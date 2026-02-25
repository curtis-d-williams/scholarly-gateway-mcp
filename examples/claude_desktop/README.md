# Claude Desktop Integration (MCP)

scholarly-gateway-mcp communicates over **stdio** using the Model Context Protocol. Claude Desktop connects to it as a local MCP server.

## Configuration

Add an entry to your Claude Desktop MCP config (typically `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "scholarly-gateway": {
      "command": "scholarly-gateway"
    }
  }
}
```

Restart Claude Desktop after saving. The server's tools (`search_works`, `get_abstract`, `forward_citations`) will appear in the tool list.

## Example tool call: search_works

```json
{
  "query": "attention is all you need",
  "sort": "citations",
  "limit": 5
}
```

Claude Desktop will send this payload to `search_works` and receive a structured response including a `results` array and a `provider_status` block.

## Checking provider_status

Every response includes a `provider_status` map. Always inspect it:

- `"ok"` — provider responded normally.
- `"not_supported"` — the operation is not available from that provider; this is expected, not an error.
- `"error"` — a transient or permanent failure; check the `message` field.

Example:

```json
"provider_status": {
  "openalex": { "status": "ok", "http_status": 200, "message": "", "retry_after_seconds": 0 },
  "arxiv":    { "status": "ok", "http_status": 200, "message": "", "retry_after_seconds": 0 }
}
```

---

> **Non-normative notice:** These examples are illustrative only. The [V1 contract](../../docs/V1_CONTRACT.md) is authoritative for all schema definitions, invariants, and behavior guarantees.
