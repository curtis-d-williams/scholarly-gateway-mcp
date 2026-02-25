# Integration Guide — scholarly-gateway-mcp V1

## What This Project Is

`scholarly-gateway-mcp` is an MCP (Model Context Protocol) server that provides a deterministic, provenance-aware gateway to scholarly publication sources. It exposes a fixed set of tools for searching, retrieving, and navigating academic works across OpenAlex and arXiv.

Every response includes structured output (the "spine" — an `InternalWork` object) alongside a Markdown view. Provenance records on every result state which provider supplied which data. Work identity is resolved by stable, deterministic keys (`work_key`, `cluster_key`).

## What This Project Is Not

- Not a ranking engine. No "best papers" output. Sort options are explicit: `relevance`, `recency`, `citations`.
- Not a synthesis or summarization layer. No claim extraction, topic modeling, or opinion generation.
- Not a full-text retrieval system. Full-text download and storage are outside V1 scope.
- Not a live index. Data comes from provider APIs at request time; the server does not maintain its own literature corpus.
- Not extensible through this guide. Do not infer or implement behavior beyond what the V1 contract defines.

---

## Quickstart

### 1. Install

```
pip install scholarly-gateway-mcp
```

### 2. Run the MCP server

```
scholarly-gateway
```

The server starts and listens for MCP tool calls over stdio (the default FastMCP transport).

### 3. Optional environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SCHOLARLY_GATEWAY_DB_PATH` | `./.data/scholarly_gateway.db` | SQLite file for cross-session lookup persistence |
| `SCHOLARLY_GATEWAY_INTEL_ENABLED` | disabled | Enable audit ledger (set to `1`, `true`, `yes`, or `on`) |
| `SCHOLARLY_GATEWAY_INTEL_DB_PATH` | `./.data/scholarly_gateway_intel.db` | SQLite file for the intel ledger |

The server functions correctly without setting any environment variable. The audit ledger is disabled by default; enabling it has no effect on tool outputs (fail-open by design).

---

## Canonical Tool Calls

### `search_works`

Search across OpenAlex and arXiv. Returns a list of `InternalWork` results and a Markdown table.

**Request parameters:**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | Free-text or identifier query |
| `year_from` | int | null | Filter by publication year (inclusive) |
| `year_to` | int | null | Filter by publication year (inclusive) |
| `kind` | string | null | `journal-article`, `preprint`, `conference-paper`, `other` |
| `oa_only` | bool | `false` | Restrict to open-access works |
| `providers` | list[string] | `["openalex","arxiv"]` | Subset providers |
| `sort` | string | `relevance` | `relevance`, `recency`, or `citations` |
| `limit` | int | `10` | Max results (hard cap: 25) |
| `cursor` | string | null | Opaque pagination token from a prior response |

**Abbreviated response structure:**

```json
{
  "schema_version": "1.0",
  "results": [ /* InternalWork[] */ ],
  "markdown": "| work_key | title | ... |",
  "next_cursor": "eyJvcGVuYWxleCI6...",
  "provider_status": {
    "openalex": { "status": "ok", "http_status": 200, "message": null, "retry_after_seconds": 0 },
    "arxiv":    { "status": "ok", "http_status": 200, "message": null, "retry_after_seconds": 0 }
  }
}
```

### `get_work`

Retrieve full details for a work by its `work_key`.

```json
{ "work_key": "wrk_<hash>" }
```

Response: full `InternalWork` spine + Markdown detail view + `provider_status`.

Note: `get_work` resolves from the in-process cache first, then from the SQLite lookup store. If the work has not been seen in the current session and is not in the persistent store, the response returns a not-found stub. Run `search_works` first to populate the cache.

### `get_abstract`

```json
{ "work_key": "wrk_<hash>", "mode": "teaser" }
```

`mode` is `teaser` (default, ~300 characters) or `full`. Full abstract retrieval for arXiv works re-fetches from the arXiv Atom feed; for OpenAlex works it reconstructs from the inverted index server-side.

### `get_fulltext_links`

```json
{ "work_key": "wrk_<hash>" }
```

Returns `links` (landing URL, PDF URL, DOI URL, arXiv abstract URL) and `access` (OA status, best OA URL).

### `forward_citations` / `backward_references`

```json
{ "work_key": "wrk_<hash>", "limit": 10, "cursor": null }
```

Both tools use OpenAlex only. arXiv returns `not_supported` for citation data. See provider_status interpretation below.

### `export_citation`

```json
{ "work_key": "wrk_<hash>", "format": "bibtex" }
```

`format` is `bibtex`, `ris`, or `csl-json`. Uses data already in cache; requires a prior `search_works` or `get_work` call.

### `compare_versions`

```json
{ "work_key": "wrk_<hash>" }
```

Returns version history for arXiv papers. Non-arXiv works return an empty version list with an explanatory message.

---

## Interpreting `provider_status`

Every tool response includes a `provider_status` map. The possible `status` values and their deterministic meanings are:

| Status | Meaning | Action |
|---|---|---|
| `ok` | Provider responded successfully | Results from this provider are present |
| `not_supported` | This tool does not use this provider in V1 | Expected; not an error condition |
| `timeout` | Provider request exceeded the timeout threshold | Results from this provider are absent; retry or use the other provider |
| `rate_limited` | Provider returned HTTP 429 | Inspect `retry_after_seconds`; back off before retrying |
| `auth_required` | Provider requires authentication not configured | Not expected in V1 for OpenAlex/arXiv public APIs |
| `error` | Any other provider-level failure | `message` field contains detail |

**Rule:** A `not_supported` status is not a failure. It is the defined V1 behavior for tools that do not use a given provider. For example, `forward_citations` and `backward_references` always return `arxiv: { "status": "not_supported" }`. Do not treat this as an error or retry it.

**Rule:** Results are partial when one provider is `ok` and another is not. The response always includes whatever succeeded. Never assume a non-`ok` status means all results are absent.

---

## Reproducibility Checklist

To make a set of results reproducible and auditable:

1. **Pin the version.** Record the installed package version (`pip show scholarly-gateway-mcp`). Output structure and tool behavior are tied to the V1 contract for a given version.

2. **Record all inputs exactly.** Save the full parameter set for each tool call: `query`, `filters`, `sort`, `limit`, `cursor` (if paginating), and `providers`. A cursor token is opaque but must be captured verbatim if the page matters.

3. **Capture the full structured output.** Save the `results` array (the `InternalWork` spine objects) in full, not just the Markdown view. The Markdown is a rendering convenience and may truncate fields. The spine is the canonical record.

4. **Record `provider_status` per call.** Document which providers were `ok`, which were `not_supported`, and which failed. This affects result completeness.

5. **Note `work_key` and `cluster_key` values.** These are deterministic hashes of the strongest available identifier. They are stable across sessions for the same underlying work, provided the identifier inputs are identical.

6. **Ledger notes (optional).** If `SCHOLARLY_GATEWAY_INTEL_ENABLED` is set, the audit ledger records `TOOL_CALL` events with a content hash. These entries can confirm that a specific call was made and what arguments were passed. See `docs/LEDGER_PHASE1.md` for invariants.

---

## Do / Don't

**Do:**

- Call `search_works` before calling `get_work`, `get_abstract`, `get_fulltext_links`, or `export_citation` in a new session. The work cache is in-process and does not persist beyond the SQLite lookup store.
- Check `provider_status` in every response before drawing conclusions about result completeness.
- Use `work_key` as the stable identifier when chaining tool calls within a session.
- Use the `providers` filter to limit a query to a single provider when you know which one is relevant.
- Record the exact `cursor` token when paginating, and use it verbatim in the next call.

**Don't:**

- Do not infer behavior not stated in `docs/V1_CONTRACT.md`. The contract is the authoritative specification.
- Do not treat `not_supported` as a transient error. It is a defined status meaning the capability does not exist in V1 for that provider.
- Do not assume `work_key` is human-readable or reversible. It is an opaque hash. Use identifiers in the `InternalWork.identifiers` field for external references.
- Do not use the Markdown output field as a data source for downstream processing. Use the structured spine.
- Do not call citation tools (`forward_citations`, `backward_references`) expecting arXiv results. These tools are OpenAlex-only in V1.
- Do not expect ranking, scoring, or synthesis beyond explicit sort ordering. The server does not rank by relevance in a semantic sense.
- Do not add tools, flags, or capabilities not in the V1 contract. The contract is frozen.
