"""AgentCore Platform v1.0 — HCR-C2-015 outer graph (Cat 2)"""

# Medical Equipment Maintenance Knowledge Base Q&A Agent — Cat 2.
#
# Architecture (per the framework's Cat 2 wrapped-subgraph pattern):
#   Outer graph (this file): AgentBaseGraph, fixed 5-node backbone.
#     initialize → pre_process → main(GraphNode) → post_process → finalize
#   Inner graph (src/graph/equipment_manual_workflow_graph.py): BaseGraph,
#     custom domain topology (equipment_lookup → manual_kb_retrieve →
#     procedure_extract → safety_check).
#
# EquipmentManualGraphNode is placed in THIS file (not src/nodes/) by design
# — by the Cat 2 wrapped-subgraph pattern: GraphNode.__call__() intentionally does
# not run the standard node lifecycle (it delegates security gating to the
# inner subgraph), so tests/proof_of_boundary/test_pb_invoke_order.py (which
# auto-discovers every BaseNode subclass under src/nodes/) must not
# accidentally pick it up.

from typing import TYPE_CHECKING, Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.nodes.output_format_node import OutputFormatNode
from src.nodes.query_normalize_node import QueryNormalizeNode
from src.schemas.state import State

if TYPE_CHECKING:
    # Type-checking only — the real import stays function-scoped in
    # get_subgraph() below to avoid the nodes -> graph -> graph.graph ->
    # nodes.main_node -> graph.subgraph circular import at runtime.
    from src.graph.equipment_manual_workflow_graph import EquipmentManualWorkflowGraph


class EquipmentManualGraphNode(GraphNode):
    """Wraps the inner equipment-manual workflow subgraph (`main` slot)."""

    # S-1: outer main-slot wrapper — first node in the outer backbone to
    # receive caller input; matches config/agent.yaml required_trust_level
    # and sibling outer nodes (QueryNormalizeNode / OutputFormatNode).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    # Fail fast on inner errors (e.g. unknown equipment, missing KB section) —
    # the caller needs an explicit ERROR status, not a degraded answer.
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any = None):
        super().__init__()
        self._llm = llm

    def get_subgraph(self) -> "EquipmentManualWorkflowGraph":
        from src.graph.equipment_manual_workflow_graph import EquipmentManualWorkflowGraph

        sg = EquipmentManualWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit the dispatch into the
        # inner subgraph (per the Cat 2 wrapped-subgraph pattern's S-4 note).
        emit_trace_event(
            "equipment_manual_workflow_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        # state is AgentState (Any-typed without SDK stubs) — cast the lookup
        # result since this node's contract always stores a str here.
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "equipment_manual_workflow_completed",
            {
                "correlation_id": state.get("correlation_id"),
                "step_count": len(sub_result.get("procedure_steps", [])),
            },
            state,
        )
        return {
            "equipment_id": sub_result.get("equipment_id"),
            "kb_namespace": sub_result.get("kb_namespace"),
            "procedure_steps": sub_result.get("procedure_steps", []),
            "tools_required": sub_result.get("tools_required", []),
            "safety_warnings": sub_result.get("safety_warnings", []),
            "kb_source_ref": sub_result.get("kb_source_ref", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm}


class HCRC2015Graph(AgentBaseGraph):
    """Medical Equipment Maintenance Knowledge Base Q&A Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "hcr-c2-015"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        llm = self.config.get("llm") if hasattr(self, "config") else None

        self._nodes["pre_process"] = QueryNormalizeNode(llm=llm)
        self._nodes["main"] = EquipmentManualGraphNode(llm=llm)
        self._nodes["post_process"] = OutputFormatNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


# agent.yaml module:"src.graph" / class:"Graph" entry point alias.
Graph = HCRC2015Graph
