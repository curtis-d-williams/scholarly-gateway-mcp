# Intelligence Layer — Architecture (Design Only)

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## Purpose

The Intelligence Layer provides persistence, provenance recording, and graph observability beneath the frozen V1 MCP surface. It does not modify tool schemas, tool outputs, identity rules, or merge semantics.

The V1 tool surface (8 tools) remains authoritative and externally unchanged.

## Architectural Boundary

The system is divided into two logical layers:

1. V1 Retrieval Substrate (Frozen)
   - Provider adapters
   - Identity normalization
   - Hard merge / soft-link semantics
   - SQLite storage
   - MCP tool surface

2. Intelligence Layer (Internal Only)
   - Citation graph persistence
   - Metadata snapshot history
   - Provenance ledger
   - Internal graph utilities

The Intelligence Layer must be removable without affecting V1 behavior.

## Non-Goals

- No new MCP tools
- No schema changes
- No ranking logic
- No scoring logic
- No probabilistic clustering
- No modification of work_key or cluster_key rules
- No changes to merge semantics
