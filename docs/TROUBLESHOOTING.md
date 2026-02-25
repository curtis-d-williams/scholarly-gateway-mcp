# Troubleshooting — scholarly-gateway-mcp V1

This document covers the top failure modes observed when using the server. Each entry is contract-aligned: the described behavior is specified in `docs/V1_CONTRACT.md` and is not speculative.

---

## 1. Provider Not Supported

**Symptom:** A tool response contains `"status": "not_supported"` for one or both providers.

**Cause:** `not_supported` is the defined V1 status for a provider that a given tool does not use. It is not a transient failure.

Defined cases in V1:
- `forward_citations` and `backward_references`: `arxiv` always returns `not_supported`. These tools use OpenAlex only.
- `search_works` with `providers: ["arxiv"]`: `openalex` returns `not_supported` because it was excluded by the caller.
- Any tool call made against a provider that is not in the active `providers` list.

**Resolution:** Do not retry `not_supported`. If citation data is needed, confirm the work has an `openalex_id` in its `identifiers` field. If the `openalex_id` is null, citation lookup is not possible for that work in V1.

**What to check:**
- Inspect `provider_status` for both providers in the response.
- Confirm the `providers` parameter in your `search_works` call includes the provider you need.
- For citation tools, check `identifiers.openalex_id` on the work before calling.

---

## 2. Network or Timeout

**Symptom:** A tool response contains `"status": "timeout"` or `"status": "error"` for a provider. Results from that provider are absent.

**Cause:** The server enforces a per-request timeout (default 10 seconds) on provider API calls. If a provider does not respond within the timeout, the call is aborted and the status is set to `timeout`.

The response always includes results from whichever providers succeeded. A timeout from one provider does not suppress results from the other.

**Resolution:**
- The response is partial, not empty. Inspect `results` for data from the provider that succeeded.
- Retry the call. Provider timeouts are typically transient.
- If the timeout is persistent, check network connectivity to `api.openalex.org` or `export.arxiv.org`.
- To restrict to a single provider while one is unavailable, use the `providers` parameter: `"providers": ["arxiv"]` or `"providers": ["openalex"]`.

**What to check:**
- `provider_status[*].status` — identify which provider timed out.
- `provider_status[*].message` — may contain a brief description of the error.
- `results` length — confirm whether partial results were returned from the other provider.

---

## 3. Rate Limit

**Symptom:** A tool response contains `"status": "rate_limited"` for a provider.

**Cause:** The provider returned HTTP 429. The server performs exponential backoff with jitter on rate limit responses, but if the limit persists through the backoff window, the status is surfaced to the caller.

**Relevant concurrency constraints from V1:**
- arXiv: max concurrency of 1 and a minimum inter-request interval. Issuing many calls in rapid succession increases the likelihood of rate limiting from arXiv.
- OpenAlex: higher concurrency allowed, but a global per-process cap is enforced. Backoff applies on 429 responses.

**Resolution:**
- Inspect `retry_after_seconds` in the `provider_status` object. If non-zero, wait that duration before retrying.
- If `retry_after_seconds` is zero or null, apply a conservative backoff (e.g., 30–60 seconds) before retrying.
- Reduce call frequency if issuing many sequential requests.

**What to check:**
- `provider_status[*].status` — confirms `rate_limited`.
- `provider_status[*].retry_after_seconds` — provider-supplied backoff hint.

---

## 4. Malformed Query

**Symptom:** `search_works` returns zero results with `provider_status` showing `ok` from both providers, or returns an error.

**Cause:** The query was syntactically valid but returned no matches, or the query triggered a provider-level error (e.g., a malformed structured query string).

The `query` parameter in `search_works` is a free-text string. Both providers interpret it independently. There is no query language validation at the gateway layer.

**Common cases:**
- Query is an identifier format (DOI, arXiv ID) but was passed to the wrong provider. For example, passing a raw DOI string like `10.1234/example` to arXiv's free-text search may return no results.
- Query contains characters that cause a provider API error (e.g., unescaped special characters).
- `year_from` / `year_to` filter is too narrow to match any records.
- `kind` filter does not match the actual document types in the result set.

**Resolution:**
- For arXiv ID lookups, pass the bare arXiv ID (e.g., `2101.03961`) as the query and restrict `providers` to `["arxiv"]`.
- For DOI lookups, pass the DOI string as the query against OpenAlex: `providers: ["openalex"]`.
- Remove or widen filters (`year_from`, `year_to`, `kind`, `oa_only`) to confirm they are not over-restricting results.
- Check `provider_status` messages for any provider-reported error detail.

**What to check:**
- `results` length in the response.
- `provider_status[*].message` — may indicate a provider-side query error.
- Applied filters — ensure they are not more restrictive than intended.

---

## 5. Install or Environment Mismatch

**Symptom:** The `scholarly-gateway` command is not found, the server fails to start, or tool calls return unexpected schema errors.

**Cause:** One of the following:
- Package is not installed in the active Python environment.
- A conflicting version of a dependency is present.
- The `scholarly-gateway` entry point is not on `PATH`.
- Python version is incompatible (V1 targets Python 3.13 or compatible).

**Resolution:**

Verify the installation:

```
pip show scholarly-gateway-mcp
```

If the package is not found, install it:

```
pip install scholarly-gateway-mcp
```

For development installs:

```
pip install -e ".[dev]"
```

Verify the entry point is available:

```
which scholarly-gateway
```

If using a virtual environment, confirm it is activated before running the server:

```
source .venv/bin/activate
scholarly-gateway
```

**Schema mismatch:** If the MCP client reports unexpected fields or missing fields, confirm the client is using a `work_key` from the current session. `work_key` values from a prior version of the server may not resolve correctly if the hash function or schema changed between releases. Pin the package version (`pip install scholarly-gateway-mcp==<version>`) to ensure consistency across sessions.

**What to check:**
- Output of `pip show scholarly-gateway-mcp` — confirms version and install path.
- Output of `which scholarly-gateway` — confirms the entry point is on PATH.
- Active virtual environment — confirm it matches the install location.
- Package version — confirm it matches the version used when results were first captured.
