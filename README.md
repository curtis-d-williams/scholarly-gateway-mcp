# scholarly-gateway-mcp

A reusable MCP (Model Context Protocol) server that provides a deterministic, provenance-aware gateway to scholarly publication sources.

## V1 Contract
Authoritative spec: `docs/V1_CONTRACT.md`

## Setup (dev)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pytest -q
```

## Run (placeholder)
The MCP server entrypoint will be added in `src/scholarly_gateway/server.py`.
