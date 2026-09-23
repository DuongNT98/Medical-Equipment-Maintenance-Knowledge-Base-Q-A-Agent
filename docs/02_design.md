# Template Design Specification — HCR-C2-015

## Position in AgentCore Architecture

- **Agent Class**: `HCRC2015Graph` (`src/graph/graph.py`, `Graph = HCRC2015Graph` alias for `agent.yaml` entry point)
- **L1 Base**: `AgentBaseGraph` (outer graph) — Cat 2 pattern: outer `AgentBaseGraph` + `GraphNode` (main slot) wrapping an inner `BaseGraph` subgraph (`EquipmentManualWorkflowGraph`, `src/graph/equipment_manual_workflow_graph.py`). No L2 inheritance anywhere in this template.
- **Three-Layer Separation**:
  - State: flat TypedDict composition (`src/schemas/state.py`, `class State(AgentState)`), every agent-specific field wrapped `NotRequired[...]`
  - Node: L1 inheritance — every node overrides only `execute(self, state: dict) -> dict`
  - Graph: composition — outer `register_nodes()` calls `super().register_nodes()` then assigns `pre_process`/`main`/`post_process`; inner `register_nodes()` assigns the 4 domain nodes, no `super()` call (BaseGraph is fully custom topology)

## Architecture Overview

### Outer node configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | `InitializeNode` (default) |
| pre_process (`QueryNormalizeNode`) | LLM: extract `equipment_model`/`maintenance_task`/`component` from the query | `user_input` | `equipment_model`, `maintenance_task`, `component`, `validated_input` (JSON) | `FunctionNode` |
| main (`EquipmentManualGraphNode`) | Dispatch to the inner subgraph (lookup → retrieve → synthesize → verbatim safety-check) | `validated_input` | `equipment_id`, `kb_namespace`, `procedure_steps`, `tools_required`, `safety_warnings`, `kb_source_ref` | `GraphNode` (main slot) |
| post_process (`OutputFormatNode`) | Assemble final answer + 医療機器法 reference + escalation path | `procedure_steps`, `tools_required`, `safety_warnings`, `kb_source_ref` | `formatted_output`, `regulatory_reference`, `escalation_path` | `FunctionNode` |
| finalize | response_metadata, total_time_ms | — | — | `FinalizeNode` (default) |

### Inner subgraph node configuration (`EquipmentManualWorkflowGraph`)

| Node | Responsibility | LLM? |
|------|-----------------|------|
| `equipment_lookup` (`EquipmentLookupNode`) | Match `equipment_model` against the maintained inventory (`EquipmentInventoryService`); reject unknown equipment | ❌ |
| `manual_kb_retrieve` (`ManualKBRetrieveNode`) | Retrieve procedure/tools/safety-warning sections from the per-manufacturer manual KB (`ManualKBService`, VectorRAG pattern) | ❌ |
| `procedure_extract` (`ProcedureExtractNode`) | Synthesize the procedure narrative from `procedure_raw`; safety_warnings is never passed to the LLM | ✅ |
| `safety_check` (`SafetyCheckNode`) | S-3 preservation-variant: enforce `safety_warnings` reaches output verbatim, never omitted/paraphrased | ❌ |

### LLM Provider (QueryNormalizeNode, ProcedureExtractNode)

Both `✅`-marked nodes resolve `shared.services.llm.azure_openai_client.AzureOpenAIClient`
fresh inside `execute()` via `InvocationContext.from_state(state).secrets.require(...)`
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` —
`config/agent.yaml` `requires.secrets` + `requires.extras: ["openai"]`). The client is
never constructed in `__init__`/`register_nodes()` and never cached on `self`: node
instances are reused across invocations/callers via the registry's LRU cache, so a
cached client built from one caller's secrets would leak to the next. `Graph(config=
{"llm": ...})` remains a separate, test-only injection seam (`tests/integration/
test_graph.py`) that takes priority over secrets resolution when present.

**Error contract (finding-recipes.md 3m — deliberately not the generic graceful-degrade
shape):** no secrets bound at all → the existing deterministic heuristic/pass-through
runs (today's default in every environment without Azure secrets provisioned). Once an
LLM **is** configured (all three secrets present), any failure — malformed
`AZURE_OPENAI_ENDPOINT`, API error, empty/unparseable response — is a hard
`status=error`; it never silently falls back to the heuristic. A configured LLM that
starts failing must be visibly broken, not silently degraded into a passing result.

### Data Flow

```
Outer:  START → initialize → pre_process(QueryNormalizeNode)
             → main(EquipmentManualGraphNode) → {route}
             → post_process(OutputFormatNode) → finalize → END
                                             ↓ (retry, max 3)
                                       pre_process

Inner (invoked by EquipmentManualGraphNode.get_subgraph()):
  START → equipment_lookup → manual_kb_retrieve → procedure_extract → safety_check → END
```

`EquipmentManualGraphNode.extract_input()` forwards `validated_input` (a JSON
string `{"equipment_model", "maintenance_task", "component"}` set by
`QueryNormalizeNode`) to the inner subgraph as `user_input`; the inner graph
does not see outer state directly (per the Cat 2 wrapped-subgraph pattern). `merge_output()`
maps the inner `get_output()` fields back into outer state.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `equipment_model` | `NotRequired[str]` | Equipment model extracted from the query | No |
| `maintenance_task` | `NotRequired[str]` | Maintenance task extracted from the query | No |
| `component` | `NotRequired[str]` | Optional component sub-scope | No |
| `equipment_id` | `NotRequired[str]` | KB-namespace reference (not PHI) | No |
| `kb_namespace` | `NotRequired[str]` | Per-manufacturer manual KB namespace | No |
| `procedure_raw` | `NotRequired[list[str]]` | Raw manual procedure steps (pre-LLM) | No |
| `tools_required` | `NotRequired[list[str]]` | Required tools list | No |
| `safety_warnings` | `NotRequired[list[str]]` | Verbatim safety warnings — never LLM-touched | No |
| `safety_warning_count` | `NotRequired[int]` | Expected warning count (preservation check anchor) | No |
| `kb_source_ref` | `NotRequired[str]` | Manual section citation | No |
| `procedure_steps` | `NotRequired[list[str]]` | LLM-synthesized procedure narrative | No |
| `regulatory_reference` | `NotRequired[str]` | 医療機器法 (PMD Act) reference string | No |
| `escalation_path` | `NotRequired[str]` | Escalation guidance | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy) — default `max_retry`/`timeout_seconds` in `config/agent.yaml` sufficient
- [ ] SecurityViolationError — not raised directly; validation failures return `AgentStatus.ERROR` dicts (fail-closed, non-raising)
- [x] S-2: default PII scan sufficient — no `_extra_security_gate_input()` override needed (no PHI/PII in scope; equipment-only queries)
- [x] S-3: `_extra_security_gate_output()` — **preservation variant** on `SafetyCheckNode`
      (re-checks that `safety_warnings` reaches its own output key with
      `len() >= safety_warning_count`; rejects any omission/truncation
      introduced between `execute()` and the gate — never filters/redacts
      content, only verifies presence, per the framework's S-3 preservation
      variant pattern)
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside
      every node's `execute()` (`query_normalized`, `equipment_lookup_completed`/
      `_rejected`, `manual_kb_retrieved`, `procedure_synthesized`,
      `safety_warnings_verified`, `output_formatted`, plus
      `equipment_manual_workflow_dispatched`/`_completed` from
      `EquipmentManualGraphNode`'s `extract_input()`/`merge_output()` hooks)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass (all 6 domain nodes here) → framework `@final` gate
>   always runs automatically; extend via `_extra_security_gate_input()` /
>   `_extra_security_gate_output()` only
> - `GraphNode` (`EquipmentManualGraphNode`) → deliberate no-op at the wrapper
>   level; each inner node runs its own `FunctionNode` gate individually

### Composition Pattern

- **Pattern**: `GraphNode` (subgraph) — Cat 2, `main` slot wraps `EquipmentManualWorkflowGraph`
- **Composition target**: `EquipmentManualWorkflowGraph` (`src/graph/equipment_manual_workflow_graph.py`)
- **Error propagation strategy**: `propagate` — inner errors (unknown equipment,
  missing KB section, safety-warning omission) surface as an explicit
  `AgentStatus.ERROR` to the caller; no silent degradation is acceptable for
  a safety-critical maintenance answer.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | `AgentBaseGraph` | `AutonomousBaseGraph` | `AgentBaseGraph` | Fixed pipeline is sufficient; no autonomous think→act loop needed |
| Composition pattern | Flat 3-slot (Cat 1 style) | `GraphNode` + inner `BaseGraph` (Cat 2) | `GraphNode` + inner `BaseGraph` | Cat 2 template — `gate-composition` requires the wrapped-subgraph pattern, not a flat MainNode absorbing multiple steps |
| Safety-warning enforcement | LLM-based summarization | S-3 preservation-variant hook (verbatim, non-LLM) | Preservation-variant hook | a resolved CoE ruling mandates verbatim safety-critical output — an LLM path risks paraphrasing/omission |
