# scholarly-gateway-mcp

A reusable MCP (Model Context Protocol) server that provides a deterministic, provenance-aware gateway to scholarly publication sources. The V1 contract is frozen; behavior and tool schemas are stable and will not change without an explicit contract revision.

## Start here

- [Integration Guide](docs/INTEGRATION_GUIDE.md) — what this server is, quickstart, canonical tool call patterns, provider_status interpretation, and a reproducibility checklist
- [Examples](docs/EXAMPLES.md) — three canonical workflows: single-provider lookup, multi-provider query with not_supported handling, and re-run determinism verification
- [Troubleshooting](docs/TROUBLESHOOTING.md) — top failure modes with contract-aligned resolution steps

## V1 Contract
Authoritative spec: [docs/V1_CONTRACT.md](docs/V1_CONTRACT.md)

## Setup (dev)

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -e ".[dev]"
    pytest -q

## Install

For local development (editable install):

    pip install -e ".[dev]"

For a regular install:

    pip install .

## Run

    scholarly-gateway

## Configuration

Environment variables:

- SCHOLARLY_GATEWAY_DB_PATH (optional): path to SQLite DB file used for cross-session lookup persistence.
  - Default: ./.data/scholarly_gateway.db
