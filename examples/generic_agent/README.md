# Generic MCP Client Integration

Minimal steps for integrating scholarly-gateway-mcp into any MCP-capable agent or client.

## Steps

1. **Start scholarly-gateway**

   ```
   scholarly-gateway
   ```

   The server listens on stdio and speaks MCP JSON-RPC.

2. **Discover tools**

   Send an `tools/list` request. The stable V1 tool surface is:
   `search_works`, `get_abstract`, `forward_citations`.

3. **Call search_works**

   Send a `tools/call` request with name `search_works` and arguments:

   ```json
   {
     "query": "attention is all you need",
     "sort": "citations",
     "limit": 5
   }
   ```

4. **Inspect provider_status**

   Every response includes a `provider_status` map keyed by provider name. Check each entry's `status` field before consuming results:

   - `"ok"` — results from this provider are present.
   - `"not_supported"` — this operation is not available from this provider; expected, not a failure.
   - `"error"` — transient or permanent failure; see `message`.

   ```json
   "provider_status": {
     "openalex": { "status": "ok", "http_status": 200, "message": "", "retry_after_seconds": 0 },
     "arxiv":    { "status": "ok", "http_status": 200, "message": "", "retry_after_seconds": 0 }
   }
   ```

5. **Use work_key as a stable identifier**

   `work_key` values are deterministic hashes derived from identifiers. The same inputs produce the same key across runs. Use `work_key` to reference a result in subsequent `get_abstract` or `forward_citations` calls.

6. **Paginate with next_cursor**

   If `next_cursor` is non-null in the response, pass it verbatim as `cursor` in the next call to retrieve the following page. Do not modify cursor values.

## Determinism and stability

- Tool schemas are frozen under the V1 contract and will not change without an explicit contract revision.
- `work_key` and `cluster_key` are stable across sessions for the same identifier inputs.
- `fetched_at` and live citation counts vary between runs; all other identity fields are stable.

---

> **Non-normative notice:** These examples are illustrative only. The [V1 contract](../../docs/V1_CONTRACT.md) is authoritative for all schema definitions, invariants, and behavior guarantees.
