"""AgentCore Platform v1.0 — HCR-C2-015 inner subgraph (equipment manual workflow)"""

# Inner graph for the Cat 2 outer EquipmentManualGraphNode (src/graph/graph.py).
# Custom domain topology (BaseGraph): equipment_lookup → manual_kb_retrieve
# → procedure_extract → safety_check.
#
# Data flow (per the Cat 2 wrapped-subgraph pattern): the inner graph does NOT see the
# outer state — only `user_input` (the JSON string set by
# QueryNormalizeNode's validated_input, forwarded by
# EquipmentManualGraphNode.extract_input()). EquipmentLookupNode parses that
# JSON back into equipment_model/maintenance_task/component.

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.equipment_lookup_node import EquipmentLookupNode
from src.nodes.manual_kb_retrieve_node import ManualKBRetrieveNode
from src.nodes.procedure_extract_node import ProcedureExtractNode
from src.nodes.safety_check_node import SafetyCheckNode
from src.schemas.state import State


class EquipmentManualWorkflowGraph(BaseGraph):
    """Inner Cat 2 workflow: lookup → retrieve → synthesize → safety-check."""

    @property
    def name(self) -> str:
        return "equipment_manual_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config keys — llm is optional (nodes fall back to a
        # deterministic heuristic/pass-through when no LLM client is bound).
        pass

    def register_nodes(self) -> None:
        # No super() call — BaseGraph.register_nodes() is abstract.
        # initialize/finalize are outer backbone concerns (graph.py).
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["equipment_lookup"] = EquipmentLookupNode()
        self._nodes["manual_kb_retrieve"] = ManualKBRetrieveNode()
        self._nodes["procedure_extract"] = ProcedureExtractNode(llm=llm)
        self._nodes["safety_check"] = SafetyCheckNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "equipment_lookup")
        self._sg.add_edge("equipment_lookup", "manual_kb_retrieve")
        self._sg.add_edge("manual_kb_retrieve", "procedure_extract")
        self._sg.add_edge("procedure_extract", "safety_check")
        self._sg.add_edge("safety_check", END)

    def route(self, state: AgentState) -> str:
        # Required by ABC — linear topology, never called (no conditional edges).
        return END if state.get("status") == AgentStatus.ERROR.value else "safety_check"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "equipment_id": state.get("equipment_id"),
            "kb_namespace": state.get("kb_namespace"),
            "procedure_steps": state.get("procedure_steps", []),
            "tools_required": state.get("tools_required", []),
            "safety_warnings": state.get("safety_warnings", []),
            "kb_source_ref": state.get("kb_source_ref", ""),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
            # EquipmentManualGraphNode.execute() (outer graph.py, error_strategy="propagate")
            # builds SubgraphError from this dict's "error_log" — omitting it here silently
            # empties every propagated error message on a real inner failure.
            "error_log": state.get("error_log", []),
        }
