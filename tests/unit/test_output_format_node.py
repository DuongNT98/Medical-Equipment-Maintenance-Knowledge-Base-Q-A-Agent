# HCR-C2-015 — Unit Tests: OutputFormatNode

from framework.schemas.agent_status import AgentStatus
from src.nodes.output_format_node import OutputFormatNode


class TestOutputFormatNode:
    def setup_method(self):
        self.node = OutputFormatNode()

    def test_success_path(self):
        state = {
            "procedure_steps": ["1. Do X", "2. Do Y"],
            "tools_required": ["screwdriver"],
            "safety_warnings": ["WARNING: A"],
            "kb_source_ref": "manufacturer_a/vent-3000/manual-v4#sec-6.2",
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert "医療機器法" in result["regulatory_reference"]
        assert result["escalation_path"]
        assert result["formatted_output"]["safety_warnings"] == ["WARNING: A"]

    def test_empty_procedure_returns_error(self):
        state = {"procedure_steps": [], "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
