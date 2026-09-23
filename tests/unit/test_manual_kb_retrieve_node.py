# HCR-C2-015 — Unit Tests: ManualKBRetrieveNode

from framework.schemas.agent_status import AgentStatus
from src.nodes.manual_kb_retrieve_node import ManualKBRetrieveNode


class TestManualKBRetrieveNode:
    def setup_method(self):
        self.node = ManualKBRetrieveNode()

    def test_success_path(self):
        state = {
            "kb_namespace": "manufacturer_a/vent-3000",
            "maintenance_task": "quarterly_inspection",
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["procedure_raw"]
        assert result["safety_warnings"]
        assert result["safety_warning_count"] == len(result["safety_warnings"])
        assert result["kb_source_ref"]

    def test_missing_section_returns_error(self):
        state = {
            "kb_namespace": "manufacturer_a/vent-3000",
            "maintenance_task": "nonexistent_task",
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR

    def test_missing_namespace_returns_error(self):
        state = {"kb_namespace": "", "maintenance_task": "", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
