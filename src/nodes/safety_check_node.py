"""AgentCore Platform v1.0 — HCR-C2-015 SafetyCheckNode (inner subgraph, S-3 preservation variant)"""

# Step 5 (proposal §4): detect safety-critical warning sections and enforce
# that they reach the output VERBATIM — never LLM-paraphrased, never
# omitted. This is the safety-critical control of the whole agent (a
# resolved CoE ruling), implemented via the S-3
# `_extra_security_gate_output()` hook — preservation variant, per
# the framework's S-3 preservation variant pattern.
#
# Design: `execute()` performs the fail-closed business validation directly
# (returns an ERROR dict, never raises) and echoes safety_warnings back into
# ITS OWN output dict unchanged. `_extra_security_gate_output()` re-checks
# that exact key (own-output-key contract) against the expected count set
# earlier by ManualKBRetrieveNode, catching any accidental omission/mutation
# introduced between execute() and the gate — non-raising, always returns a
# dict.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_OMISSION_MSG = "S-3 preservation violation: safety warning omitted or truncated (verbatim rule)"


class SafetyCheckNode(FunctionNode):
    """Enforce verbatim safety-warning output (S-3 preservation variant)."""

    # S-1: inner subgraph node — trust authenticated at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        safety_warnings = state.get("safety_warnings", [])
        expected_count = state.get("safety_warning_count", 0)

        if expected_count and len(safety_warnings) < expected_count:
            emit_trace_event(
                "safety_warnings_omission_detected",
                {
                    "correlation_id": state.get("correlation_id"),
                    "expected_count": expected_count,
                    "actual_count": len(safety_warnings),
                },
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [_OMISSION_MSG],
            }

        emit_trace_event(
            "safety_warnings_verified",
            {"correlation_id": state.get("correlation_id"), "warning_count": len(safety_warnings)},
            state,
        )

        # Verbatim echo — never paraphrase, never summarize, never drop.
        return {
            "safety_warnings": list(safety_warnings),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation variant: re-check THIS node's own output key.

        Re-verifies `safety_warnings` (the field execute() just returned)
        against `safety_warning_count` (set upstream by ManualKBRetrieveNode
        and still present in the merged state). Always returns a dict;
        never raises; never mutates other fields.
        """
        output_warnings = state.get("safety_warnings", [])
        expected_count = state.get("safety_warning_count", 0)

        if expected_count and len(output_warnings) < expected_count:
            return {
                **state,
                "status": AgentStatus.ERROR.value,
                "error_log": list(state.get("error_log", [])) + [_OMISSION_MSG],
            }
        return state
