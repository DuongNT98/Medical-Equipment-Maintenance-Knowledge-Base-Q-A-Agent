"""AgentCore Platform v1.0 — HCR-C2-015 ProcedureExtractNode (inner subgraph)"""

# Step 4 (proposal §4): synthesize the procedure narrative from procedure_raw
# (LLM). Safety-critical sections (safety_warnings) are NEVER passed through
# the LLM here — they were already set verbatim by ManualKBRetrieveNode and
# this node deliberately does not touch that field; SafetyCheckNode (step 5)
# is the enforcement point. Inner subgraph node — ANONYMOUS.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets import MissingSecret
from shared.services.llm.azure_openai_client import AzureOpenAIClient
from shared.utils.audit_logger import emit_trace_event


class ProcedureExtractNode(FunctionNode):
    """Synthesize the procedure narrative from the raw manual section."""

    # S-1: inner subgraph node — trust authenticated at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None):
        # Injection seam for tests (Graph(config={"llm": FakeLLM()}) — see
        # tests/integration/test_graph.py). The real Azure client is never
        # constructed here or in register_nodes(): when this stays None, it is
        # resolved fresh per-invocation inside _synthesize() from ctx.secrets,
        # never cached on self (node instances are registry-LRU-cached and
        # reused across invocations/callers).
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        procedure_raw = state.get("procedure_raw", [])
        maintenance_task = state.get("maintenance_task", "")

        if not procedure_raw:
            emit_trace_event(
                "procedure_extract_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty_procedure_raw"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ProcedureExtractNode: procedure_raw is empty from ManualKBRetrieveNode"],
            }

        procedure_steps, llm_failed = self._synthesize(procedure_raw, maintenance_task, state)
        if llm_failed:
            emit_trace_event(
                "procedure_extract_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "llm_call_failed"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "ProcedureExtractNode: LLM is configured but returned no usable response — "
                    "not falling back to the deterministic pass-through (finding-recipes.md 3m: a "
                    "configured LLM failure must not be silently swallowed into SUCCESS)"
                ],
            }

        emit_trace_event(
            "procedure_synthesized",
            {"correlation_id": state.get("correlation_id"), "step_count": len(procedure_steps)},
            state,
        )

        # NOTE: safety_warnings is intentionally NOT returned here — it is
        # left untouched in state (still the verbatim value set by
        # ManualKBRetrieveNode) so no LLM synthesis path can paraphrase it.
        return {
            "procedure_steps": procedure_steps,
            "status": AgentStatus.SUCCESS.value,
        }

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalise a BaseLLM.complete() result (canonical dict or a test-fake string)."""
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""

    def _resolve_llm(self, state: dict[str, Any]) -> Any:
        """Return a configured LLM client, or None when none is configured.

        A constructor-injected test double (self._llm) wins first. Otherwise
        resolve Azure OpenAI fresh from ctx.secrets — never cached on self,
        since node instances are reused across invocations/callers (registry
        LRU cache). A MissingSecret means no LLM is configured at all (the
        deterministic pass-through is the valid path); any other failure while
        building the client (e.g. a malformed AZURE_OPENAI_ENDPOINT) means an
        LLM IS configured but broken, so it must surface as a hard error, not
        a silent fallback (finding-recipes.md 3m) — the caller distinguishes
        the two by catching only MissingSecret here.
        """
        if self._llm is not None:
            return self._llm
        try:
            ctx = InvocationContext.from_state(state)
        except (KeyError, TypeError, ValueError):
            # No full lifecycle-identity state (e.g. a bare unit-test state
            # dict) — no real invoke path reaches here without those fields,
            # so this is equivalent to "not configured", not "configured but
            # broken". GraphNode.execute() indexes these fields, not .get().
            return None
        try:
            return AzureOpenAIClient(
                {
                    "api_key": ctx.secrets.require("AZURE_OPENAI_API_KEY"),
                    "azure_endpoint": ctx.secrets.require("AZURE_OPENAI_ENDPOINT"),
                    "azure_deployment": ctx.secrets.require("AZURE_OPENAI_DEPLOYMENT"),
                }
            )
        except MissingSecret:
            return None

    def _synthesize(
        self, procedure_raw: list[str], maintenance_task: str, state: dict[str, Any]
    ) -> tuple[list[str], bool]:
        """Turn the raw manual steps into a numbered procedure narrative.

        Returns (steps, llm_failed). `llm_failed=True` only when an LLM IS
        configured but its response could not be normalised into usable
        lines — the caller must surface this as a hard error, not silently
        degrade to the deterministic pass-through below (that pass-through is
        only valid when no LLM is configured at all — finding-recipes.md 3m).
        """
        try:
            llm = self._resolve_llm(state)
        except Exception:
            # LLM IS configured (secrets present) but the client itself could not
            # be built (e.g. a malformed AZURE_OPENAI_ENDPOINT) — hard error, same
            # as a failed .complete() call below, never a silent pass-through.
            return [], True
        if llm is not None:
            try:
                narrative = llm.complete(
                    [
                        {
                            "role": "user",
                            "content": (
                                f"Rewrite these maintenance steps for task '{maintenance_task}' as a "
                                f"clear numbered procedure, one step per line: {procedure_raw}"
                            ),
                        }
                    ]
                )
                text = self._extract_text(narrative)
                if text.strip():
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    if lines:
                        return lines, False
                return [], True
            except Exception:
                return [], True

        # Deterministic pass-through — only reached when no LLM is configured
        # at all (no test-double injected and no secrets bound).
        return [f"{i + 1}. {step}" for i, step in enumerate(procedure_raw)], False
