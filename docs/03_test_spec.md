# Test Specification — HCR-C2-015

## Test Strategy
- Coverage target: all BL paths (unit + integration); hard % threshold enforced by CI gate
- Test types: Unit (per node) / Integration (full graph compile+invoke) / Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | SecurityViolationError fires on invalid input | Error raised (fail-closed `AgentStatus.ERROR` dict, non-raising) | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | PASS (CI gate) |
| TC-04 | InvocationContext via configurable only | Direct access raises error | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | PASS |
| TC-09 | S-2: `_extra_security_gate_input()` — default scan sufficient | No PHI/PII in scope (equipment-only); no domain override needed | N/A by design |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial — `SafetyCheckNode` preservation variant | Rejects output where `safety_warnings` omits/truncates below `safety_warning_count` | PASS |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path (all 6 nodes + GraphNode hooks) | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | PASS |
| PB-3 | L1 → External service | `ManualKBService`/`EquipmentInventoryService` retrieval via L1 framework | Data retrieved (reference in-memory KB; pluggable for a real backend) | PASS |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | PASS |
| PB-5 | Checkpoint safety | State-definition scan (no JWT/Pydantic) + checkpoint/ingress-safety test | State scan: inspection pass. Ingress test: auto-waived — neither `memory_enabled` nor `hitl.enabled` is set, so nothing is checkpointed | PASS (state scan) / SKIP (ingress test, by design) |
| PB-6 | Invoke execution order + S-1 denial (TC-08) | `test_pb_invoke_order.py` (scaffold-canonical, copied verbatim) | Order verified; under-privileged caller denied at S-1 before `execute()` | PASS |
| PB-7 | HITL interrupt propagation | `test_pb7_hitl_interrupt_propagation.py` — `hitl.enabled` is absent/false for this template | Auto-skips (N/A — no HITL in scope) | SKIP (by design) |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Full pipeline: known equipment + task | `VENT-3000 quarterly_inspection` | `status=SUCCESS`, non-empty `procedure_steps`/`safety_warnings`/`regulatory_reference` | PASS |
| BL-02 | Unknown equipment rejected | `UNKNOWN-9999 some_task` | `status=ERROR` from `EquipmentLookupNode`, no procedure surfaced | PASS |
| BL-03 | Safety warning omission blocked by S-3 preservation variant | `safety_warnings` truncated below `safety_warning_count` | `SafetyCheckNode._extra_security_gate_output()` returns `status=ERROR` | PASS |
| BL-04 | Empty query | `""` | `QueryNormalizeNode` returns `status=ERROR` (no LLM call attempted) | PASS |
| BL-05 | LLM configured (Azure secrets bound), well-formed response | `AZURE_OPENAI_API_KEY`/`ENDPOINT`/`DEPLOYMENT` bound via `ctx.secrets`, no constructor `llm=` | `QueryNormalizeNode`/`ProcedureExtractNode` resolve `AzureOpenAIClient` fresh per-invocation and use its response — `status=SUCCESS` | PASS |
| BL-06 | LLM configured, malformed `AZURE_OPENAI_ENDPOINT` (contains `/openai` path) | Secrets bound, endpoint carries a path | Client construction raises `ValueError` (no network call) → `status=ERROR`, never a silent heuristic fallback | PASS |
| BL-07 | No LLM configured (no secrets bound, no constructor `llm=`) | Standard invoke with empty `SecretProvider` (`NullProvider`) | Deterministic heuristic/pass-through runs — `status=SUCCESS` (today's default in every environment without Azure secrets provisioned) | PASS |

## Test Execution Summary
- Execution date: 2026-09-18 (SDK/scaffold reintegration — `agenticstar-agentcore==1.0.3`)
- Total tests: 69 passed, 3 skipped (`pytest tests/ -q`) — 2 HITL not-applicable
  (this template has no HITL) + 1 PB-5 checkpoint/ingress test auto-waived
  (neither `memory_enabled` nor `hitl.enabled` is set)
- Pass: all local-runnable tests pass, including PB-6 (`test_pb_invoke_order.py`,
  installed from the registry wheel — no local-mirror gap on 1.0.3)
- Coverage: all BL paths (unit + integration) exercised, including the LLM
  provider wiring (BL-05/06/07); hard % threshold enforced by CI gate
