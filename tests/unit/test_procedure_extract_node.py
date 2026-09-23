# HCR-C2-015 — Unit Tests: ProcedureExtractNode

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from framework.secrets import SecretProvider, bound_secrets
from src.nodes.procedure_extract_node import ProcedureExtractNode


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
    "caller_trust_level": TrustLevel.ANONYMOUS.value,
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
        return "1. Do the first thing\n2. Do the second thing"


class FakeLLM:
    def complete(self, *_a, **_k):
        return "1. Do the first thing\n2. Do the second thing"


class CanonicalDictLLM:
    """Canonical BaseLLM.complete() shape — {"content": str, ...} — regression
    test for finding-recipes.md 3m (dict result must not be discarded)."""

    def complete(self, *_a, **_k):
        return {"content": "1. Do the first thing\n2. Do the second thing", "tool_calls": [], "model": "fake-model"}


class EmptyContentLLM:
    def complete(self, *_a, **_k):
        return {"content": "", "tool_calls": [], "model": "fake-model"}


class RaisingLLM:
    def complete(self, *_a, **_k):
        raise ValueError("provider timeout")


class TestProcedureExtractNode:
    def test_success_path_with_llm(self):
        node = ProcedureExtractNode(llm=FakeLLM())
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "safety_warnings": ["WARNING: do not touch."],
            "node_history": [],
            "error_log": [],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert len(result["procedure_steps"]) == 2
        # safety_warnings must NOT be returned/altered by this node — it bypasses
        # the LLM entirely and is left untouched in state.
        assert "safety_warnings" not in result

    def test_fallback_pass_through_without_llm(self):
        node = ProcedureExtractNode(llm=None)
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["procedure_steps"] == ["1. Step A", "2. Step B"]

    def test_empty_procedure_raw_returns_error(self):
        node = ProcedureExtractNode()
        state = {"procedure_raw": [], "maintenance_task": "x", "node_history": [], "error_log": []}
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR

    def test_canonical_dict_llm_response_is_used(self):
        node = ProcedureExtractNode(llm=CanonicalDictLLM())
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["procedure_steps"]) == 2

    def test_configured_llm_empty_response_is_error_not_fallback(self):
        node = ProcedureExtractNode(llm=EmptyContentLLM())
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_configured_llm_raising_is_error_not_fallback(self):
        node = ProcedureExtractNode(llm=RaisingLLM())
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]

    def test_secrets_bound_resolves_and_uses_llm(self, monkeypatch):
        # Production shape: no constructor llm, real secrets bound — resolves
        # AzureOpenAIClient fresh from ctx.secrets and uses its response.
        monkeypatch.setattr("src.nodes.procedure_extract_node.AzureOpenAIClient", FakeAzureClient)
        provider = _FakeSecretProvider(
            {
                "AZURE_OPENAI_API_KEY": "k",
                "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT": "d",
            }
        )
        node = ProcedureExtractNode(llm=None)
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
            **_FULL_STATE_EXTRAS,
        }
        with bound_secrets(provider):
            result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert len(result["procedure_steps"]) == 2

    def test_secrets_bound_with_malformed_endpoint_is_error_not_fallback(self):
        # Secrets present but AZURE_OPENAI_ENDPOINT carries a path — the real
        # AzureOpenAIClient rejects it (no network call). Configured-but-broken
        # must be a hard error, not a silent pass-through.
        provider = _FakeSecretProvider(
            {
                "AZURE_OPENAI_API_KEY": "k",
                "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com/openai/v1/responses",
                "AZURE_OPENAI_DEPLOYMENT": "d",
            }
        )
        node = ProcedureExtractNode(llm=None)
        state = {
            "procedure_raw": ["Step A", "Step B"],
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
            **_FULL_STATE_EXTRAS,
        }
        with bound_secrets(provider):
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_log"]
