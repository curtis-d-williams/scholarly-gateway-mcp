
# TEST_STRATEGY.md
**Intelligence Layer — Contract Preservation Test Strategy (Design Only)**

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## 1) Purpose

This strategy defines the **minimum test suite** required to ensure that any Intelligence Layer implementation (Option 3) **cannot introduce contract drift** in V1:

- Tool list remains exactly 8
- Tool schemas remain unchanged
- Tool outputs remain unchanged (golden tests)
- Determinism holds (same input → same output)
- Intelligence layer failures never affect tool responses (fail-open)

This is intended to be directly implemented and used in CI.

---

## 2) Test Types (Minimum Set)

### T1 — Tool Surface Freeze Test
**Goal:** Assert exactly 8 tools and exact names.

**Mechanism:**
- Instantiate the MCP server (or the tool registry object used by FastMCP).
- Enumerate tool names.
- Assert the set equals:

- search_works
- get_work
- get_abstract
- get_fulltext_links
- forward_citations
- backward_references
- export_citation
- compare_versions

**Pass Criteria:**
- Same names, same count, no extras.

---

### T2 — Schema Snapshot Freeze Test
**Goal:** Prevent accidental input/output schema drift.

**Mechanism:**
- Serialize each tool's input schema and output schema (canonical JSON).
- Compare against committed snapshots in `tests/schema_snapshots/`.

**Snapshot Files (suggested):**
- `tests/schema_snapshots/tools.json`
  - tool names + schema digests
- `tests/schema_snapshots/<tool>.input.schema.json`
- `tests/schema_snapshots/<tool>.output.schema.json`

**Pass Criteria:**
- Byte-identical match (or sha256 digest match of canonical JSON).

**Update Rule:**
- Snapshots may only change with explicit Curtis approval.

---

### T3 — Golden Output Tests (Contract Output Equality)
**Goal:** Ensure tool responses do not change.

**Mechanism:**
- For each selected test case, run the tool and compare the serialized output to a committed golden file.

**Golden Files Location (suggested):**
- `tests/golden/<tool>/<case>.json` (or `.md` if markdown output)

**Important:** Live providers are nondeterministic. Golden tests must use one of:
- **Record/Replay** fixtures (HTTP cassette / provider response fixtures), or
- Provider stubs/mocks.

**Pass Criteria:**
- Output matches golden exactly after canonical serialization.

---

### T4 — Determinism Tests (Within-Run Repeatability)
**Goal:** Catch hidden nondeterminism (ordering, timestamps, random IDs).

**Mechanism:**
- Run each golden case twice in one test run.
- Assert output1 == output2 (same serialization).

**Pass Criteria:**
- Byte-identical.

---

### T5 — Fail-Open Intelligence Layer Test
**Goal:** Intel failures must not affect tool responses.

**Mechanism:**
- Enable intelligence layer via internal env var (if/when implemented).
- Force intel write failure (e.g., invalid intel DB path / permission denied / injected exception).
- Run the same golden test case.
- Assert output matches golden exactly.

**Pass Criteria:**
- Tool output unchanged, no raised error to caller.

---

## 3) Minimal Fixture Set (Non-Clutter)

Keep fixtures minimal: **1–2 cases per tool**, focusing on representative paths.

Suggested cases:

### search_works
- `arxiv_id_lookup`: query `id:2010.11929` (via stubbed provider response)

### get_work
- `doi_lookup`: a known DOI response fixture

### get_abstract
- `abstract_present`: fixture with abstract
- (optional) `abstract_missing`: fixture with no abstract to confirm stable null behavior

### get_fulltext_links
- `fulltext_links`: fixture with multiple links

### forward_citations / backward_references
- `citations_small_graph`: small graph fixture with 2–5 edges (enough to validate stability)

### export_citation
- `bibtex_export`: deterministic bibtex formatting fixture

### compare_versions
- `no_change`: same record twice fixture
- (optional) `one_field_change`: one metadata field differs fixture

**Rule:** Add more fixtures only when a real bug or regression requires it.

---

## 4) Canonical Serialization Rules (To Prevent False Diffs)

Before comparing outputs to goldens:

- Sort JSON object keys (canonical JSON)
- For lists:
  - Only sort if order is explicitly non-semantic in V1
  - Otherwise preserve provider-defined order exactly
- Strip runtime-only fields if and only if they are explicitly excluded by V1 (ideally none)

The goal is: **compare what callers see**, not incidental runtime formatting.

---

## 5) CI Gates (What Must Block Merges)

CI must fail if any of these fail:

- T1 Tool Surface Freeze
- T2 Schema Snapshot Freeze
- T3 Golden Output Tests
- T4 Determinism Tests
- T5 Fail-Open (only once intel is implemented)

Additionally, CI should fail if `docs/V1_CONTRACT.md` changes unless explicitly permitted.

---

## 6) Updating Goldens / Snapshots (Strict Process)

Goldens and schema snapshots should be treated as contract artifacts.

Allowed reasons to update:
- A deliberate contract version change (not planned under V1), or
- A documented bugfix where the previous output violated V1 contract language

Approval:
- Curtis must approve any updates to:
  - schema snapshots
  - golden outputs

---

## 7) Implementation Order (Fast Path)

Safest acceleration order:

1) Implement T1 + T2 first (cheap, strong guardrails)
2) Add record/replay fixtures and T3 + T4 for the minimal fixture set
3) Only then implement intelligence layer behind flag
4) Add T5 to prove fail-open

This ensures you never "build on sand."
