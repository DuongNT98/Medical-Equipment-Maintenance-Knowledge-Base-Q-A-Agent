"""AgentCore Platform v1.0 — HCR-C2-015 EquipmentLookupNode (inner subgraph)"""

# Step 2 (proposal §4): match equipment_model to a KB namespace and validate
# against the maintained inventory; reject unknown equipment. No LLM — pure
# deterministic lookup. Runs INSIDE the inner subgraph invoked via GraphNode
# (src/graph/graph.py) — trust is authenticated once at the outer backbone,
# so this inner node declares ANONYMOUS (see security-5layer-checklist.md
# S-1: inner subgraph node = ANONYMOUS, escalating here would be a
# privilege-escalation finding).

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.equipment_inventory_service import EquipmentInventoryService


class EquipmentLookupNode(FunctionNode):
    """Validate equipment_model against the maintained inventory."""

    # S-1: inner subgraph node — trust authenticated at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, inventory_service: EquipmentInventoryService | None = None):
        self._inventory_service = inventory_service or EquipmentInventoryService()

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = self._parse_input(state.get("user_input", ""))
        equipment_model = payload.get("equipment_model", "")
        maintenance_task = payload.get("maintenance_task", "")
        component = payload.get("component", "")

        if not equipment_model or not maintenance_task:
            emit_trace_event(
                "equipment_lookup_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_input_fields"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["EquipmentLookupNode: missing equipment_model/maintenance_task in inner input"],
            }

        record = self._inventory_service.lookup(equipment_model)
        if record is None:
            emit_trace_event(
                "equipment_lookup_rejected",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"EquipmentLookupNode: unknown equipment '{equipment_model}' — not in maintained inventory"
                ],
            }

        emit_trace_event(
            "equipment_lookup_completed",
            {"correlation_id": state.get("correlation_id"), "kb_namespace": record["kb_namespace"]},
            state,
        )

        return {
            "equipment_model": equipment_model,
            "maintenance_task": maintenance_task,
            "component": component,
            "equipment_id": record["equipment_id"],
            "kb_namespace": record["kb_namespace"],
            "status": AgentStatus.SUCCESS.value,
        }

    @staticmethod
    def _parse_input(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}
