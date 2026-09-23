# HCR-C2-015 — Integration Test: full graph compile + invoke

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from src.graph.graph import Graph


class FakeLLM:
    def complete(self, messages, *_a, **_k):
        # Canonical BaseLLM.complete(messages: list) -> dict contract.
        text = " ".join(m.get("content", "") for m in messages) if isinstance(messages, list) else str(messages)
        if "Extract" in text:
            content = json.dumps({"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""})
        else:
            content = "1. Power down the ventilator.\n2. Inspect the filter housing."
        return {"content": content, "tool_calls": [], "model": "fake-model"}


class TestHCRC2015Graph:
    def setup_method(self):
        self.agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
        self.agent.compile()

    def _ctx(self, session_id="it-1"):
        return InvocationContext(session_id=session_id, caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="test-caller")

    def test_success_path_known_equipment(self):
        result = self.agent.invoke("VENT-3000 quarterly_inspection", ctx=self._ctx())
        assert result.get("status") in (AgentStatus.SUCCESS.value, AgentStatus.SUCCESS)
        nh = result.get("node_history") or []
        assert len(nh) >= 5

    def test_empty_input_returns_error_or_cancelled(self):
        result = self.agent.invoke("", ctx=self._ctx(session_id="it-2"))
        assert result.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR, AgentStatus.CANCELLED.value, AgentStatus.CANCELLED)
