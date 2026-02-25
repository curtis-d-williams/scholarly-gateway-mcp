# Unified Research Gateway MCP — V1 Contract Spec (Authoritative)

## 0) Scope and Non-Scope

### V1 Scope
- Multi-provider search + retrieval with dedup/clustering, provenance, version awareness, citation navigation hooks, token-efficient outputs.
- Providers: OpenAlex + arXiv (minimum).
- Output: Markdown view + structured spine (never Markdown-only).

### Explicit Non-Scope (V1)
- No ranking beyond explicit user-specified sort (recency, citations).
- No “best papers,” no synthesis, no claim extraction, no topic modeling.
- No full-text download/storage by default.

---

## 1) Roles and Execution Discipline (Claude Code Safety)

- Curtis: Product owner + final reviewer. Approves contract changes.
- ChatGPT: Architect/reviewer. Produces specs, test cases, and review checklists.
- Claude Code: Executor only. Implements exactly what the spec states. No design expansion.

Rule: Any change to tool schemas, ID formats, or merge policy requires updating this spec + updating tests.

---

## 2) Core Concepts

### 2.1 Identifiers (Normalized)
- doi_norm: lowercase; strip leading https://doi.org/ or doi:; trim whitespace.
- arxiv_id_norm: canonical arXiv ID (e.g., 2101.12345 or hep-th/9901001); keep version separately.
- openalex_id: preserve as returned (stable URL-like ID).

### 2.2 Internal Keys
- work_key (stable): deterministic hash of strongest available identifier in priority order:
  1) doi_norm
  2) pmid (reserved for later)
  3) arxiv_id_norm
  4) fallback: title+first_author+year (normalized) ONLY for temporary referencing; flagged key_strength="weak".

- cluster_key (stable): hash of canonical “cluster identity”:
  - If DOI present: doi_norm
  - Else if arXiv id present: arxiv_id_norm
  - Else: fallback weak cluster on title+author+year with cluster_strength="weak".

Constraint: work_key format must never change once published.

---

## 3) Merge / Link Policy (Identity Resolution)

### 3.1 Hard Merge (single InternalWork)
Only when shared hard identifier matches:
- Same doi_norm, OR
- Same arxiv_id_norm, OR
- Same openalex_id (within OpenAlex only)

Hard-merged records remain listed under provenance.records[].

### 3.2 Soft Link (do not collapse)
If no shared hard identifier, but high similarity (optional V1):
- title similarity + author overlap + year proximity
Then:
- Return as separate InternalWorks with linked_candidates[] references
- match_basis="similarity" and confidence set
- Never collapse automatically in V1

### 3.3 Preprint vs Published
- Preprint and VoR may be hard merged only via DOI match.
- Otherwise they remain separate but may be soft linked.

---

## 4) Internal Data Object (IDO) — V1 Minimal Schema

```json
{
  "schema_version": "1.0",
  "work_key": "wrk_<stable>",
  "cluster_key": "clu_<stable>",
  "key_strength": "strong|weak",
  "kind": "journal-article|preprint|conference-paper|other",

  "identifiers": {
    "doi": "10....",
    "arxiv_id": "2101.12345",
    "openalex_id": "https://openalex.org/W..."
  },

  "bibliographic": {
    "title": "string",
    "authors_preview": ["A. Author", "B. Author"],
    "publication_year": 2024,
    "publication_date": "YYYY-MM-DD",
    "venue": "string|null"
  },

  "status": {
    "review_status": "preprint|peer-reviewed|unknown",
    "status_source": "arxiv|openalex|inferred"
  },

  "abstract": {
    "teaser": "string|null",
    "has_full": true
  },

  "links": {
    "landing_url": "string|null",
    "pdf_url": "string|null",
    "doi_url": "string|null",
    "arxiv_abs_url": "string|null"
  },

  "access": {
    "is_open_access": true,
    "best_oa_url": "string|null"
  },

  "metrics_preview": {
    "cited_by_count": 123
  },

  "provenance": {
    "records": [
      {
        "provider": "openalex|arxiv",
        "record_id": "string",
        "source_url": "string|null",
        "fetched_at": "ISO-8601",
        "match_basis": "id|doi|arxiv_id|similarity",
        "confidence": 0.0
      }
    ]
  },

  "linked_candidates": [
    { "work_key": "wrk_...", "confidence": 0.0, "basis": "similarity" }
  ]
}
```

Token rule: authors_preview default ≤ 3. Full authors only via detail tool.

---

## 5) Tool Surface (MCP Tools)

### 5.1 search_works
Input
- query: string
- filters: { year_from?, year_to?, kind?, oa_only?, providers? }
- sort: "relevance|recency|citations" (default relevance)
- limit: int (default 10, max 25)
- cursor?: string (for pagination)

Output
- schema_version
- results: InternalWork[] (minimal schema)
- markdown: string (table/list view; includes work_key in first column)
- next_cursor?: string
- provider_status: { openalex: StatusObj, arxiv: StatusObj }

### 5.2 get_work
Input: work_key  
Output: InternalWork (may include expanded authors, more links)

### 5.3 get_abstract
Input: work_key, mode: "teaser|full"  
Output: { work_key, mode, abstract_text, source_provider }  
- If OpenAlex uses abstract_inverted_index, reconstruction happens server-side.

### 5.4 get_fulltext_links
Input: work_key  
Output: { work_key, links, access }

### 5.5 forward_citations / backward_references (hooks)
Input: work_key, limit, cursor?  
Output: list of InternalWork minimal + next_cursor + provider_status  
(V1 may implement only via OpenAlex; arXiv can be not_supported)

### 5.6 export_citation
Input: work_key, format: "bibtex|ris|csl-json"  
Output: { work_key, format, citation_text }

### 5.7 compare_versions
Input: work_key  
Output: { work_key, versions: [...], diff_summary_markdown }  
(V1: arXiv version diffs + whether DOI/journal_ref present)

---

## 6) Error Envelope and Partial Results

### 6.1 Provider Status Object
```json
{
  "status": "ok|timeout|rate_limited|auth_required|error|not_supported",
  "http_status": 200,
  "message": "string",
  "retry_after_seconds": 0
}
```

### 6.2 Partial Results Rule
- Tool returns whatever providers succeeded.
- Never silently omit providers; always set provider_status.

### 6.3 Fail-Closed Identity Rule
- If identifiers conflict, do not merge; emit separate works + linkage candidate.

---

## 7) Concurrency + Rate-Limit Governance

- All provider calls are async.
- Per-provider limiters:
  - arXiv: max_concurrency=1 and minimum inter-request interval enforced.
  - OpenAlex: higher concurrency allowed; enforce global per-process cap and backoff on 429.
- Timeouts:
  - provider request timeout default 10s (configurable).
- Backoff: exponential + jitter on 429/5xx; circuit-breaker after N failures.

---

## 8) Pagination Contract

- cursor is an opaque token created by the gateway.
- Must encode: provider cursors + normalized query params + sort.
- Must be stable for at least TTL window of cached search results.

---

## 9) Token Efficiency Rules

- Default responses exclude:
  - full authorship lists
  - full abstract text (except teaser)
  - reference/citation lists
  - concepts/keywords/mesh/topics (future enrichment)
- All large fields retrieved via explicit tools (get_abstract, citations tools).

---

## 10) Test Requirements (Minimal but Mandatory)

- Unit tests:
  1) DOI normalization
  2) arXiv ID/version parsing
  3) hard-merge behavior on DOI
  4) “no merge” on similarity-only
  5) stable work_key determinism

- Fixtures:
  - saved sample OpenAlex response
  - saved sample arXiv Atom feed entry
  - at least 1 preprint-without-DOI case and 1 preprint-with-DOI case
