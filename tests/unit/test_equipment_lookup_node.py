# HCR-C2-015 — Unit Tests: EquipmentLookupNode

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.equipment_lookup_node import EquipmentLookupNode


class TestEquipmentLookupNode:
    def setup_method(self):
        self.node = EquipmentLookupNode()

    def test_success_path_known_equipment(self):
        state = {
            "user_input": json.dumps({"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""}),
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS
        assert result["equipment_id"] == "EQ-VENT-3000-001"
        assert result["kb_namespace"] == "manufacturer_a/vent-3000"

    def test_unknown_equipment_rejected(self):
        state = {
            "user_input": json.dumps({"equipment_model": "UNKNOWN-9999", "maintenance_task": "some_task", "component": ""}),
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
        assert any("unknown equipment" in msg.lower() for msg in result["error_log"])

    def test_empty_input_returns_error(self):
        state = {"user_input": "", "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR
