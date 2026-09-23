"""AgentCore Platform v1.0 — HCR-C2-015 QueryNormalizeNode (outer pre_process)"""

# Node contract (per the framework's node implementation rules):
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes
#  - Return AgentStatus enum constants — never plain strings
#  - Never import from mediator/, api/, or other agents
#
# Step 1 (proposal §4): extract equipment_model / maintenance_task / component
# from the caller's free-text or structured query. Only an equipment_id
# REFERENCE is kept in state — no PHI (equipment only, no patient data).
# Outer node (agent boundary) — trust level matches config/agent.yaml
# (VERIFIED_EXTERNAL: professional-access scope, biomedical engineers only).

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets import MissingSecret
from shared.services.llm.azure_openai_client import AzureOpenAIClient
from shared.utils.audit_logger import emit_trace_event


class QueryNormalizeNode(FunctionNode):
    """Extract equipment_model / maintenance_task / component from the query."""

    # S-1: outer boundary node — matches agent.yaml required_trust_level
    # (professional-access scope: biomedical engineers, not public-facing).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None):
        # Injection seam for tests (Graph(config={"llm": FakeLLM()}) — see
        # tests/integration/test_graph.py). The real Azure client is never
        # constructed here or in register_nodes(): when this stays None, it is
        # resolved fresh per-invocation inside _extract() from ctx.secrets,
        # never cached on self (node instances are registry-LRU-cached and
        # reused across invocations/callers).
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")
        if not user_input or not user_input.strip():
            emit_trace_event(
                "query_normalize_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty_input"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["QueryNormalizeNode: user_input is empty or missing"],
            }

        extracted, llm_failed = self._extract(user_input, state)
        if llm_failed:
            emit_trace_event(
                "query_normalize_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "llm_call_failed"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "QueryNormalizeNode: LLM is configured but returned no usable response — "
                    "not falling back to the deterministic heuristic (finding-recipes.md 3m: a "
                    "configured LLM failure must not be silently swallowed into SUCCESS)"
                ],
            }

        equipment_model = extracted.get("equipment_model", "")
        maintenance_task = extracted.get("maintenance_task", "")
        component = extracted.get("component", "")

        if not equipment_model or not maintenance_task:
            emit_trace_event(
                "query_normalize_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "extraction_failed"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["QueryNormalizeNode: could not extract equipment_model/maintenance_task from query"],
            }

        validated_input = json.dumps(
            {
                "equipment_model": equipment_model,
                "maintenance_task": maintenance_task,
                "component": component,
            },
            ensure_ascii=False,
        )

        emit_trace_event(
            "query_normalized",
            {
                "correlation_id": state.get("correlation_id"),
                "has_component": bool(component),
            },
            state,
        )

        return {
            "equipment_model": equipment_model,
            "maintenance_task": maintenance_task,
            "component": component,
            "validated_input": validated_input,
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
        deterministic heuristic is the valid path); any other failure while
        building the client (e.g. a malformed AZURE_OPENAI_ENDPOINT) means an
        LLM IS configured but broken, so it must surface as a hard error, not
        a silent heuristic fallback (finding-recipes.md 3m) — the caller
        distinguishes the two by catching only MissingSecret here.
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

    def _extract(self, user_input: str, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Extract entities from the query.

        Returns (extracted_fields, llm_failed). `llm_failed=True` only when an
        LLM IS configured but its response could not be normalised into a
        usable entity dict — the caller must surface this as a hard error, not
        silently degrade to the deterministic heuristic below (that heuristic
        is only valid when no LLM is configured at all — finding-recipes.md 3m).
        """
        try:
            llm = self._resolve_llm(state)
        except Exception:
            # LLM IS configured (secrets present) but the client itself could not
            # be built (e.g. a malformed AZURE_OPENAI_ENDPOINT) — hard error, same
            # as a failed .complete() call below, never a silent heuristic fallback.
            return {}, True
        if llm is not None:
            try:
                raw = llm.complete(
                    [
                        {
                            "role": "user",
                            "content": (
                                "Extract equipment_model, maintenance_task, and component (optional) "
                                f"as a JSON object from this maintenance query: {user_input}"
                            ),
                        }
                    ]
                )
                text = self._extract_text(raw)
                if not text:
                    return {}, True
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return {
                        "equipment_model": str(parsed.get("equipment_model", "")).strip(),
                        "maintenance_task": str(parsed.get("maintenance_task", "")).strip(),
                        "component": str(parsed.get("component", "") or "").strip(),
                    }, False
                return {}, True
            except Exception:
                return {}, True

        # Deterministic fallback heuristic — only reached when no LLM is
        # configured at all (no test-double injected and no secrets bound).
        parts = user_input.strip().split()
        equipment_model = parts[0] if parts else ""
        maintenance_task = "_".join(p.lower() for p in parts[1:]) if len(parts) > 1 else ""
        component = ""
        if "component:" in user_input:
            component = user_input.split("component:", 1)[1].strip()
            maintenance_task = maintenance_task.split("component")[0].strip("_")
        return {
            "equipment_model": equipment_model,
            "maintenance_task": maintenance_task,
            "component": component,
        }, False
