# Canonical Workflow Examples — scholarly-gateway-mcp V1

These examples show concrete tool call patterns and expected response structures.
All examples stay within the V1 contract. `work_key` and hash values shown are illustrative placeholders — actual values are computed server-side.

---

## Workflow 1: Single-Provider arXiv ID Lookup

**Goal:** Retrieve a known arXiv paper by ID, using arXiv only.

### Step 1 — Search with arXiv as the sole provider

Tool: `search_works`

```json
{
  "query": "2101.03961",
  "providers": ["arxiv"],
  "limit": 1
}
```

Expected response (abbreviated):

```json
{
  "schema_version": "1.0",
  "results": [
    {
      "work_key": "wrk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "cluster_key": "clu_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
      "key_strength": "strong",
      "kind": "preprint",
      "identifiers": {
        "doi": null,
        "arxiv_id": "2101.03961",
        "openalex_id": null
      },
      "bibliographic": {
        "title": "Example Paper Title",
        "authors_preview": ["A. Author", "B. Author"],
        "publication_year": 2021,
        "publication_date": "2021-01-11",
        "venue": null
      },
      "status": {
        "review_status": "preprint",
        "status_source": "arxiv"
      },
      "abstract": {
        "teaser": "First ~300 characters of abstract...",
        "has_full": true
      },
      "links": {
        "landing_url": "https://arxiv.org/abs/2101.03961",
        "pdf_url": "https://arxiv.org/pdf/2101.03961",
        "doi_url": null,
        "arxiv_abs_url": "https://arxiv.org/abs/2101.03961"
      },
      "access": {
        "is_open_access": true,
        "best_oa_url": "https://arxiv.org/pdf/2101.03961"
      },
      "metrics_preview": { "cited_by_count": null },
      "provenance": {
        "records": [
          {
            "provider": "arxiv",
            "record_id": "2101.03961",
            "source_url": "http://export.arxiv.org/api/query?...",
            "fetched_at": "2026-02-25T12:00:00Z",
            "match_basis": "arxiv_id",
            "confidence": 1.0
          }
        ]
      },
      "linked_candidates": []
    }
  ],
  "markdown": "| work_key | title | year | kind | oa | providers |\n|---|...",
  "next_cursor": null,
  "provider_status": {
    "openalex": { "status": "not_supported", "message": null, "retry_after_seconds": 0 },
    "arxiv":    { "status": "ok",            "http_status": 200, "message": null, "retry_after_seconds": 0 }
  }
}
```

Key observations:
- `openalex.status = "not_supported"` because `providers` excluded OpenAlex. This is expected and correct.
- `key_strength = "strong"` because the arXiv ID is a hard identifier.
- `doi` is null. This is a preprint with no DOI in the arXiv record.

### Step 2 — Retrieve full abstract

Tool: `get_abstract`

```json
{
  "work_key": "wrk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "mode": "full"
}
```

Expected response:

```json
{
  "work_key": "wrk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "mode": "full",
  "abstract_text": "Full abstract text as returned by the arXiv Atom feed.",
  "source_provider": "arxiv"
}
```

---

## Workflow 2: Multi-Provider Query with One Provider Not Supported for Citations

**Goal:** Search both providers, then retrieve forward citations — noting that arXiv is `not_supported` for citation data.

### Step 1 — Search both providers

Tool: `search_works`

```json
{
  "query": "attention is all you need",
  "sort": "citations",
  "limit": 5
}
```

Expected `provider_status` when both providers respond:

```json
"provider_status": {
  "openalex": { "status": "ok", "http_status": 200, "message": null, "retry_after_seconds": 0 },
  "arxiv":    { "status": "ok", "http_status": 200, "message": null, "retry_after_seconds": 0 }
}
```

Select a `work_key` from the results where `identifiers.openalex_id` is non-null. Citation lookups require an OpenAlex ID.

### Step 2 — Forward citations

Tool: `forward_citations`

```json
{
  "work_key": "wrk_<hash-of-work-with-openalex-id>",
  "limit": 10
}
```

Expected response structure:

```json
{
  "work_key": "wrk_<hash>",
  "results": [ /* InternalWork[] of citing works */ ],
  "markdown": "...",
  "next_cursor": "eyJvcGVuYWxleCI6...",
  "provider_status": {
    "openalex": { "status": "ok",            "http_status": 200, "message": null, "retry_after_seconds": 0 },
    "arxiv":    { "status": "not_supported", "message": "Not supported by this provider in V1", "retry_after_seconds": 0 }
  }
}
```

Key observations:
- `arxiv.status = "not_supported"` is the defined behavior. arXiv does not provide citation data in V1. Do not retry against arXiv.
- All citation results come from OpenAlex only.
- If the work has no `openalex_id`, `openalex.status` will be `"error"` with the message `"No OpenAlex ID available for citation lookup"` and `results` will be empty. This is not a transient failure — it means the work was not found in OpenAlex.

### Step 3 — Paginate if needed

If `next_cursor` is non-null, pass it verbatim to the next call:

```json
{
  "work_key": "wrk_<hash>",
  "limit": 10,
  "cursor": "eyJvcGVuYWxleCI6..."
}
```

The cursor encodes the provider-specific pagination state. It is opaque and must not be modified.

---

## Workflow 3: Re-Run and Verify Determinism

**Goal:** Confirm that a prior result is reproducible by re-running the same query and comparing the canonical output.

### What must match

For two runs of the same `search_works` call to be considered deterministically equivalent:

| Field | Must match |
|---|---|
| `work_key` | Yes — same identifier inputs produce the same hash |
| `cluster_key` | Yes — same derivation rules |
| `key_strength` | Yes |
| `identifiers.*` | Yes — the identifier values are provider-supplied |
| `bibliographic.*` | Should match; minor variation possible if provider updates metadata between calls |
| `provider_status[*].status` | Yes, for the same network conditions and providers |
| `provenance.records[*].match_basis` | Yes |
| `provenance.records[*].confidence` | Yes |

### What may differ between runs

- `provenance.records[*].fetched_at` — this is a timestamp set at fetch time.
- `bibliographic.cited_by_count` — OpenAlex citation counts update continuously.
- `abstract.teaser` — content is provider-supplied; updates if the provider updates the record.
- `next_cursor` — cursor tokens encode time-bound state and are not stable across sessions.

### How to compare

1. Run `search_works` with identical parameters. Capture the full `results` array as canonical JSON.
2. Extract `work_key` values. These are stable identifiers.
3. Compare `work_key` sets between the two runs. A paper present in one run but absent in another indicates a provider ranking or availability difference, not a server-side bug.
4. For a specific work, compare the `identifiers` block and `provenance.records[*].match_basis`. If `work_key` matches and `match_basis` matches, the identity resolution was consistent.
5. Do not compare `fetched_at` or live citation counts as invariants.

### Ledger-assisted verification (optional)

If `SCHOLARLY_GATEWAY_INTEL_ENABLED=1`, each tool call writes a `TOOL_CALL` event to the ledger with a SHA-256 content hash of the payload. The ledger entry is idempotent: the same canonical call produces the same `event_id`. This provides a tamper-evident record that a specific call was made.

To confirm a prior call was recorded: query the ledger DB (`scholarly_gateway_intel.db`) for the `event_id` corresponding to the canonical form of the call parameters. The `payload_sha256` field on the row will match the SHA-256 of the canonical payload JSON. See `docs/LEDGER_PHASE1.md` for invariant definitions.
