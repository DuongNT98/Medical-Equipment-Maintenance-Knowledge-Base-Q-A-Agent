"""AgentCore Platform v1.0 — HCR-C2-015 OutputFormatNode (outer post_process)"""

# Step 6 (proposal §4): assemble the final answer — procedure steps, tools,
# verbatim safety warnings, 医療機器法 (PMD Act) regulatory reference,
# escalation path, kb_source_ref. Outer node (agent boundary) — trust level
# matches config/agent.yaml.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_REGULATORY_REFERENCE = "医療機器法 (PMD Act) — equipment maintenance / safety-warning fidelity requirement"
_ESCALATION_PATH = "Unresolved or ambiguous procedure → escalate to the clinical-engineering department head"


class OutputFormatNode(FunctionNode):
    """Format the final procedure + safety-warning answer."""

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        procedure_steps = state.get("procedure_steps", [])
        tools_required = state.get("tools_required", [])
        safety_warnings = state.get("safety_warnings", [])
        kb_source_ref = state.get("kb_source_ref", "")

        if not procedure_steps:
            emit_trace_event(
                "output_format_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty_procedure_steps"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputFormatNode: no procedure_steps to format"],
            }

        formatted_output = {
            "procedure_steps": procedure_steps,
            "tools_required": tools_required,
            "safety_warnings": safety_warnings,
            "regulatory_reference": _REGULATORY_REFERENCE,
            "escalation_path": _ESCALATION_PATH,
            "kb_source_ref": kb_source_ref,
        }

        emit_trace_event(
            "output_formatted",
            {
                "correlation_id": state.get("correlation_id"),
                "step_count": len(procedure_steps),
                "safety_warning_count": len(safety_warnings),
            },
            state,
        )

        return {
            "formatted_output": formatted_output,
            "regulatory_reference": _REGULATORY_REFERENCE,
            "escalation_path": _ESCALATION_PATH,
            "status": AgentStatus.SUCCESS.value,
        }
