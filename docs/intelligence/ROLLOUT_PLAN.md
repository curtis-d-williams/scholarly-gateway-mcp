# Intelligence Layer — Rollout Plan (Design Only)

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## Phase 1 — Passive Recording

- Record edges and snapshots during normal V1 execution.
- Do not alter tool outputs.
- Swallow intelligence-layer write failures.

## Phase 2 — Internal Utilities

- Internal graph traversal
- Internal metadata drift inspection

Not exposed as MCP tools.

## Phase 3 — Optional Future Versioning

Any exposure of intelligence capabilities requires explicit contract revision.
