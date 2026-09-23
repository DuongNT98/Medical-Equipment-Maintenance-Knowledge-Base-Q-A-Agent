# HCR-C2-015 — Framework compliance tests TC-01..TC-08 (verified on the real wheel).
# Adapted from a sibling template's reference shape for the Cat 2 outer(pre/post) +
# GraphNode(main)+inner-subgraph architecture of this template.

import os
import re

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import (
    equipment_lookup_node,
    manual_kb_retrieve_node,
    output_format_node,
    procedure_extract_node,
    query_normalize_node,
    safety_check_node,
)
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 — State is a flat TypedDict, no Pydantic/dataclass, agent-specific
# fields present and NotRequired-wrapped.
class TestTC01StateContract:
    def test_state_extends_agent_state(self):
        from framework.schemas.agent_state import AgentState

        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_agent_specific_fields_declared(self):
        from framework.schemas.agent_state import AgentState

        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert "equipment_model" in added
        assert "safety_warnings" in added
        assert "procedure_steps" in added


# TC-02 — Domain validation path (empty input) yields a fail-closed outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = query_normalize_node.QueryNormalizeNode()
        out = node({"caller_trust_level": TRUST, "user_input": "", "node_history": [], "error_log": []})
        assert out["status"] == AgentStatus.ERROR.value


# TC-03 — No JWT / API keys / secrets in src/.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # server.py's INVOKE_AUTH_TOKEN read is the framework's documented
        # entry-point exception — excluded from this scan by design.
        offenders = []
        for fp in _src_files():
            if fp.endswith(os.path.join("api", "server.py")):
                continue
            with open(fp, encoding="utf-8") as f:
                if "os.environ" in f.read():
                    offenders.append(fp)
        assert offenders == []


# TC-04 — InvocationContext is never stored in State.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        class FakeLLM:
            def complete(self, *_a, **_k):
                return '{"equipment_model": "VENT-3000", "maintenance_task": "quarterly_inspection", "component": ""}'

        g = Graph(config={"llm": FakeLLM()})
        g.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        out = g.invoke("VENT-3000 quarterly_inspection", ctx=ctx)
        for v in out.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 — Each node emits >=1 domain event; never backbone lifecycle events.
class TestTC05Audit:
    @pytest.mark.parametrize(
        "module,cls,state",
        [
            (
                query_normalize_node,
                "QueryNormalizeNode",
                {"caller_trust_level": TRUST, "user_input": "VENT-3000 quarterly_inspection", "node_history": [], "error_log": []},
            ),
            (
                safety_check_node,
                "SafetyCheckNode",
                {
                    "caller_trust_level": TrustLevel.ANONYMOUS.value,
                    "safety_warnings": ["WARNING: A"],
                    "safety_warning_count": 1,
                    "node_history": [],
                    "error_log": [],
                },
            ),
            (
                output_format_node,
                "OutputFormatNode",
                {
                    "caller_trust_level": TRUST,
                    "procedure_steps": ["1. Step"],
                    "tools_required": [],
                    "safety_warnings": [],
                    "kb_source_ref": "x",
                    "node_history": [],
                    "error_log": [],
                },
            ),
            # Error/reject paths — S-4 must trace every execute() path, not just success
            # (finding-recipes.md 3a "sot path": emit only at end of success path is a gap).
            (
                query_normalize_node,
                "QueryNormalizeNode",
                {"caller_trust_level": TRUST, "user_input": "", "node_history": [], "error_log": []},
            ),
            (
                equipment_lookup_node,
                "EquipmentLookupNode",
                {
                    "caller_trust_level": TrustLevel.ANONYMOUS.value,
                    "user_input": "",
                    "node_history": [],
                    "error_log": [],
                },
            ),
            (
                manual_kb_retrieve_node,
                "ManualKBRetrieveNode",
                {"caller_trust_level": TrustLevel.ANONYMOUS.value, "node_history": [], "error_log": []},
            ),
            (
                procedure_extract_node,
                "ProcedureExtractNode",
                {"caller_trust_level": TrustLevel.ANONYMOUS.value, "node_history": [], "error_log": []},
            ),
            (
                safety_check_node,
                "SafetyCheckNode",
                {
                    "caller_trust_level": TrustLevel.ANONYMOUS.value,
                    "safety_warnings": [],
                    "safety_warning_count": 2,
                    "node_history": [],
                    "error_log": [],
                },
            ),
            (
                output_format_node,
                "OutputFormatNode",
                {"caller_trust_level": TRUST, "procedure_steps": [], "node_history": [], "error_log": []},
            ),
        ],
    )
    def test_domain_event_emitted(self, module, cls, state, monkeypatch):
        events = []
        payloads = []

        def _record(e, p, s):
            events.append(e)
            payloads.append(p)

        monkeypatch.setattr(module, "emit_trace_event", _record)
        getattr(module, cls)()(state)
        assert len(events) >= 1
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))
        # Payload must be counts/correlation_id only — never raw content/PII.
        for payload in payloads:
            for key, value in payload.items():
                if key in ("correlation_id", "reason"):
                    continue
                assert isinstance(value, (int, bool)), (
                    f"{cls} emitted a non-count payload field {key!r}={value!r} — "
                    "S-4 payload must be counts/correlation_id only, not raw content"
                )

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 — S-2/S-3 gates are @final (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_overridable_and_non_trivial(self):
        # SafetyCheckNode's _extra_security_gate_output is the S-3
        # preservation-variant hook — must differ from the framework default
        # (non-trivial domain check), not just an inherited no-op.
        assert safety_check_node.SafetyCheckNode._extra_security_gate_output is not FunctionNode._extra_security_gate_output

    def test_output_gate_blocks_credentials(self):
        # The @final S-3 credential scan actually fires (not vacuous): a
        # credential in the result is blocked, never returned silently.
        node = output_format_node.OutputFormatNode()
        with pytest.raises(Exception):
            node._security_gate_output({"formatted_output": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 — required_trust_level enforced: insufficient trust → ERROR state (no raise).
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            query_normalize_node.QueryNormalizeNode,
            safety_check_node.SafetyCheckNode,
            output_format_node.OutputFormatNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        node = query_normalize_node.QueryNormalizeNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": "VENT-3000 quarterly_inspection", "node_history": [], "error_log": []})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = query_normalize_node.QueryNormalizeNode()
        out = node({"caller_trust_level": TRUST, "user_input": "VENT-3000 quarterly_inspection", "node_history": [], "error_log": []})
        assert out["status"] == AgentStatus.SUCCESS.value
