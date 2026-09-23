"""AgentCore Platform v1.0 — HCR-C2-015 state schema"""

# ADR-005: State must be a flat TypedDict. LangGraph checkpoints use msgpack
# serialization, so only plain serializable fields are allowed. Do NOT add
# credentials, secrets, or Pydantic/dataclass instances.
#
# All agent-specific fields are wrapped in NotRequired[...] (CoE C8): a field
# absent from the checkpoint, or read before it is written earlier in the
# pipeline, must not raise KeyError / msgpack-resume errors.

from typing import NotRequired

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """HCR-C2-015 Medical Equipment Maintenance Knowledge Base Q&A Agent state.

    Shared fields (user_input, status, session_id, node_history, error_log,
    hitl_*, etc.) are inherited from AgentState — do not redeclare them here.
    """

    # mypy cannot see that AgentState (and therefore State) is a TypedDict at
    # runtime without SDK stubs (agenticstar-agentcore ships no py.typed
    # marker), so it rejects every NotRequired[...] field below as "used
    # outside a TypedDict definition". This is a stub-visibility limitation,
    # not a code error — every field really is optional/JSON-safe at runtime,
    # verified by the full pytest suite and the PB-2/PB-5 state-safety tests.

    # Extracted by QueryNormalizeNode (outer pre_process, LLM).
    equipment_model: NotRequired[str]  # type: ignore[valid-type]
    maintenance_task: NotRequired[str]  # type: ignore[valid-type]
    component: NotRequired[str]  # type: ignore[valid-type]

    # equipment_id is a KB-namespace REFERENCE only (resolved by
    # EquipmentLookupNode inside the inner subgraph) — never a patient/PHI
    # identifier; this agent has no PHI in scope.
    equipment_id: NotRequired[str]  # type: ignore[valid-type]

    # Set by EquipmentLookupNode (inner) once the equipment is matched
    # against the maintained inventory.
    kb_namespace: NotRequired[str]  # type: ignore[valid-type]

    # Set by ManualKBRetrieveNode (inner).
    procedure_raw: NotRequired[list[str]]  # type: ignore[valid-type]
    tools_required: NotRequired[list[str]]  # type: ignore[valid-type]
    safety_warnings: NotRequired[list[str]]  # type: ignore[valid-type]
    safety_warning_count: NotRequired[int]  # type: ignore[valid-type]
    kb_source_ref: NotRequired[str]  # type: ignore[valid-type]

    # Set by ProcedureExtractNode (inner, LLM narrative synthesis). Safety
    # warnings are NEVER passed through the LLM — they bypass verbatim from
    # procedure_raw/safety_warnings straight to SafetyCheckNode.
    procedure_steps: NotRequired[list[str]]  # type: ignore[valid-type]

    # Set by OutputFormatNode (outer post_process).
    regulatory_reference: NotRequired[str]  # type: ignore[valid-type]
    escalation_path: NotRequired[str]  # type: ignore[valid-type]
