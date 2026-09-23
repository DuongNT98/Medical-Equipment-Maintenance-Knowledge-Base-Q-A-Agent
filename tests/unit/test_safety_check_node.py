# HCR-C2-015 — Unit Tests: SafetyCheckNode (S-3 preservation variant)

from framework.schemas.agent_status import AgentStatus
from src.nodes.safety_check_node import SafetyCheckNode


class TestSafetyCheckNode:
    def setup_method(self):
        self.node = SafetyCheckNode()

    def test_success_path_verbatim_echo(self):
        state = {
            "safety_warnings": ["WARNING: A", "WARNING: B"],
            "safety_warning_count": 2,
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["safety_warnings"] == ["WARNING: A", "WARNING: B"]

    def test_no_warnings_expected_still_succeeds(self):
        state = {"safety_warnings": [], "safety_warning_count": 0, "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS

    def test_execute_rejects_omitted_warnings(self):
        state = {
            "safety_warnings": ["WARNING: A"],
            "safety_warning_count": 2,  # upstream said 2, only 1 present — omission
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
        assert any("omitted" in msg.lower() for msg in result["error_log"])

    def test_extra_security_gate_output_passes_when_preserved(self):
        """Direct hook call (per code-contracts.md test recipe) — valid state."""
        state = {
            "safety_warnings": ["WARNING: A", "WARNING: B"],
            "safety_warning_count": 2,
            "error_log": [],
        }
        result = self.node._extra_security_gate_output(state)
        assert isinstance(result, dict)
        assert result.get("status") != AgentStatus.ERROR

    def test_extra_security_gate_output_rejects_when_omitted(self):
        """Direct hook call — violating state (fewer warnings than expected)."""
        state = {
            "safety_warnings": ["WARNING: A"],
            "safety_warning_count": 3,
            "error_log": [],
        }
        result = self.node._extra_security_gate_output(state)
        assert isinstance(result, dict)
        assert result["status"] == AgentStatus.ERROR
        assert any("preservation" in msg.lower() for msg in result["error_log"])

    def test_extra_security_gate_output_never_raises(self):
        """Hook must always return a dict, never raise — even with minimal state."""
        result = self.node._extra_security_gate_output({})
        assert isinstance(result, dict)
