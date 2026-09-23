# HCR-C2-015 — Unit Tests: QueryNormalizeNode

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from framework.secrets import SecretProvider, bound_secrets
from src.nodes.query_normalize_node import QueryNormalizeNode


class _FakeSecretProvider(SecretProvider):
    def __init__(self, values: dict):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


_FULL_STATE_EXTRAS = {
    "correlation_id": "c1",
    "session_id": "s1",
    "thread_id": None,
    "trace_id": "t1",
    "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
    "caller_id": "",
    "message_id": None,
    "request_source": None,
}


class FakeAzureClient:
    """Stands in for shared.services.llm.azure_openai_client.AzureOpenAIClient —
    no real network call anywhere in this suite."""

    def __init__(self, config):
        self.config = config

    def complete(self, *_a, **_k):
        return json.dumps({"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""})


class FakeLLM:
    def complete(self, *_a, **_k):
        return json.dumps({"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""})


class CanonicalDictLLM:
    """Returns the canonical BaseLLM.complete() shape — {"content": str, ...} —
    to regression-test finding-recipes.md 3m (dict result must not be silently
    discarded / treated as empty-extraction)."""

    def complete(self, *_a, **_k):
        return {
            "content": json.dumps(
                {"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""}
            ),
            "tool_calls": [],
            "model": "fake-model",
        }


class EmptyContentLLM:
    """Canonical dict shape but empty content — a configured-but-failing LLM."""

    def complete(self, *_a, **_k):
        return {"content": "", "tool_calls": [], "model": "fake-model"}


class RaisingLLM:
    def complete(self, *_a, **_k):
        raise ValueError("provider timeout")


class TestQueryNormalizeNode:
    def setup_method(self):
        self.node = QueryNormalizeNode(llm=FakeLLM())

    def test_success_path(self):
        state = {"user_input": "VENT-3000 quarterly maintenance check", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["equipment_model"] == "VENT-3000"
        assert result["maintenance_task"] == "quarterly_inspection"
        payload = json.loads(result["validated_input"])
        assert payload["equipment_model"] == "VENT-3000"

    def test_empty_input_returns_error(self):
        state = {"user_input": "", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
        assert result["error_log"]

    def test_fallback_heuristic_without_llm(self):
        node = QueryNormalizeNode(llm=None)
        state = {"user_input": "VENT-3000 quarterly_inspection", "node_history": [], "error_log": []}
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["equipment_model"] == "VENT-3000"

    def test_canonical_dict_llm_response_is_used(self):
        # finding-recipes.md 3m: a canonical {"content": ...} dict response must
        # be extracted and used, not silently discarded into empty extraction.
        node = QueryNormalizeNode(llm=CanonicalDictLLM())
        state = {"user_input": "VENT-3000 quarterly maintenance check", "node_history": [], "error_log": []}
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["equipment_model"] == "VENT-3000"

    def test_configured_llm_empty_response_is_error_not_fallback(self):
        # 3m silent-swallow trap: a configured LLM that returns empty content
        # must surface AgentStatus.ERROR — never a silent deterministic-fallback SUCCESS.
        node = QueryNormalizeNode(llm=EmptyContentLLM())
        state = {"user_input": "VENT-3000 quarterly maintenance check", "node_history": [], "error_log": []}
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_configured_llm_raising_is_error_not_fallback(self):
        node = QueryNormalizeNode(llm=RaisingLLM())
        state = {"user_input": "VENT-3000 quarterly maintenance check", "node_history": [], "error_log": []}
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_secrets_bound_resolves_and_uses_llm(self, monkeypatch):
        # Production shape: no constructor llm, real secrets bound — resolves
        # AzureOpenAIClient fresh from ctx.secrets and uses its response.
        monkeypatch.setattr("src.nodes.query_normalize_node.AzureOpenAIClient", FakeAzureClient)
        provider = _FakeSecretProvider(
            {
                "AZURE_OPENAI_API_KEY": "k",
                "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT": "d",
            }
        )
        node = QueryNormalizeNode(llm=None)
        state = {
            "user_input": "VENT-3000 quarterly maintenance check",
            "node_history": [],
            "error_log": [],
            **_FULL_STATE_EXTRAS,
        }
        with bound_secrets(provider):
            result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["equipment_model"] == "VENT-3000"

    def test_secrets_bound_with_malformed_endpoint_is_error_not_fallback(self):
        # Secrets present but AZURE_OPENAI_ENDPOINT carries a path — the real
        # AzureOpenAIClient rejects it (no network call). Configured-but-broken
        # must be a hard error, not a silent heuristic fallback.
        provider = _FakeSecretProvider(
            {
                "AZURE_OPENAI_API_KEY": "k",
                "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com/openai/v1/responses",
                "AZURE_OPENAI_DEPLOYMENT": "d",
            }
        )
        node = QueryNormalizeNode(llm=None)
        state = {
            "user_input": "VENT-3000 quarterly maintenance check",
            "node_history": [],
            "error_log": [],
            **_FULL_STATE_EXTRAS,
        }
        with bound_secrets(provider):
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_trust_gate_denies_anonymous_caller(self):
        state = {
            "user_input": "VENT-3000 quarterly maintenance check",
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "node_history": [],
            "error_log": [],
        }
        result = self.node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert any("trust gate" in msg.lower() for msg in result.get("error_log", []))
