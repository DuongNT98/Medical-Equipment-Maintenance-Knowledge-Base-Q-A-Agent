"""AgentCore Platform v1.0 — HCR-C2-015 ManualKBRetrieveNode (inner subgraph)"""

# Step 3 (proposal §4): retrieve procedure / tools / safety-warning /
# inspection sections from the equipment-manual KB (VectorRAG pattern —
# retrieval only, no LLM in this hop). Inner subgraph node — ANONYMOUS
# (trust authenticated at the outer backbone).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.manual_kb_service import ManualKBService


class ManualKBRetrieveNode(FunctionNode):
    """Retrieve procedure/tools/safety-warning sections from the manual KB."""

    # S-1: inner subgraph node — trust authenticated at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, kb_service: ManualKBService | None = None):
        self._kb_service = kb_service or ManualKBService()

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        kb_namespace = state.get("kb_namespace", "")
        maintenance_task = state.get("maintenance_task", "")

        if not kb_namespace or not maintenance_task:
            emit_trace_event(
                "manual_kb_retrieve_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_input_fields"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ManualKBRetrieveNode: missing kb_namespace/maintenance_task from EquipmentLookupNode"],
            }

        section = self._kb_service.retrieve(kb_namespace, maintenance_task)
        if section is None:
            emit_trace_event(
                "manual_kb_retrieve_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "section_not_found"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"ManualKBRetrieveNode: no manual section found for '{kb_namespace}'/'{maintenance_task}'"
                ],
            }

        safety_warnings = list(section.get("safety_warnings", []))

        emit_trace_event(
            "manual_kb_retrieved",
            {
                "correlation_id": state.get("correlation_id"),
                "section_count": len(section.get("procedure_raw", [])),
                "safety_warning_count": len(safety_warnings),
            },
            state,
        )

        return {
            "procedure_raw": list(section.get("procedure_raw", [])),
            "tools_required": list(section.get("tools_required", [])),
            "safety_warnings": safety_warnings,
            "safety_warning_count": len(safety_warnings),
            "kb_source_ref": section.get("kb_source_ref", ""),
            "status": AgentStatus.SUCCESS.value,
        }
