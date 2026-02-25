# Ledger Phase 1 — Design Reference

## What Exists

### Feature Flag
- Env var: `SCHOLARLY_GATEWAY_INTEL_ENABLED` (truthy: `1`, `true`, `yes`, `on`; default: disabled)
- Env var: `SCHOLARLY_GATEWAY_INTEL_DB_PATH` (default: `./.data/scholarly_gateway_intel.db`)

### Source Files
| File | Role |
|---|---|
| `src/scholarly_gateway/intel.py` | Feature-flag check, `IntelSink` (fail-open wrapper), `get_intel_sink()` |
| `src/scholarly_gateway/intel_ledger.py` | `IntelLedger` — SQLite append-only writer, `canonical_json`, `_sha256_hex` |

### Database Schema (single table)
```sql
CREATE TABLE IF NOT EXISTS ledger_event (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    source_provider TEXT,
    work_key        TEXT,
    payload_json    TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL
)
```

### Event Type
One event type: `TOOL_CALL`.
No other event types exist or will be added in Phase 1.

---

## Phase 1 Freeze Statement

**Freeze date:** 2026-02-25

**Scope:** The intel ledger is audit/observability infrastructure only. `TOOL_CALL` is the sole event type and no additional event types will be added in Phase 1. The ledger is fail-open — any initialisation or write failure must not affect tool outputs. There are no production read paths; all `SELECT` access is confined to the test suite. No derived semantics are built from ledger data: no graph or citation edges, no ranking or scoring signals, no identity registry.

**Enforcement:** The test suite covers idempotency (I1), canonicalization stability (I2), integrity (I3), fail-open behaviour (I4), and multi-tool emission coverage.

**Phase 2 rule:** Any addition of read APIs, derived semantics, new event types, or schema changes requires an explicit human product decision and a new written contract or spec reviewed by the architect before any code is written. Do not implement Phase 2 features under this document.

---

## Phase 1 Invariants

### I1 — Idempotency
Recording the exact same canonical event any number of times yields exactly one DB row with the same `event_id`.
Mechanism: `INSERT OR IGNORE` keyed on `event_id` (SHA-256 of the full canonical event dictionary excluding `event_id` itself).

### I2 — Canonicalization Stability
`canonical_json` is defined as `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
This function must not be changed without a corresponding migration; its output determines `event_id`.

### I3 — Integrity
`event_id = sha256(canonical_json({event_type, observed_at, payload_json, payload_sha256, source_provider, work_key}))`
`payload_sha256 = sha256(canonical_json(payload))`
Both fields are stored and verified in tests. A stored row's `event_id` must always be reproducible from its sibling columns alone.

### I4 — Fail-Open
Any failure during intel initialisation or write **must not** affect tool outputs.
- `get_intel_sink()` catches all exceptions and returns `None`.
- `IntelSink.record_event()` catches all exceptions silently.
- Server's `_intel()` memoizes `None` on failure; tool call paths always succeed regardless.

### I5 — No Production Reads
The ledger has no read paths in production code. `SELECT` queries are permitted only inside the test suite for row counting and value validation.

---

## Explicit Non-Goals (Phase 1)

- **No ranking or scoring** — the ledger is passive provenance, not signal for search ordering.
- **No citation graph** — no edges between works, no citation count updates.
- **No citation edges** — `work_key` on a ledger row is an informational field only; no foreign-key graph is built.
- **No identity registry** — the ledger does not resolve or unify author identities.
- **No analytics queries** — no aggregation, frequency counting, or trend detection at runtime.
- **No additional event types** — only `TOOL_CALL` exists; new event types require an explicit Phase 2 decision.
- **No schema migrations** — Phase 1 schema is final; any change requires a new phase decision.

---

## Phase 2 Trigger Conditions

Phase 2 work requires an explicit product decision and spec update before implementation. Triggers that would warrant a Phase 2 decision include:

1. **Operational need for ledger reads in production** — e.g., deduplication at query time, cache warming from ledger history.
2. **New event types required** — e.g., provenance for citation lookups, identity resolution events.
3. **Schema evolution required** — adding columns, new tables, or indexes needed for a concrete use case.
4. **Volume thresholds** — if ledger size or write latency becomes measurable in production benchmarks.
5. **Graph or ranking integration** — if ledger data is proposed as input to any ranking or scoring function.

All Phase 2 work must begin with a written spec change reviewed by the architect before any code is written.
