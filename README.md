# scholarly-gateway-mcp

A reusable MCP (Model Context Protocol) server that provides a deterministic, provenance-aware gateway to scholarly publication sources.

## V1 Contract
Authoritative spec: docs/V1_CONTRACT.md

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
