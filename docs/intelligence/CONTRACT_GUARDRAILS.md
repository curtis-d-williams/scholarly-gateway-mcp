# Intelligence Layer — Contract Guardrails (Design Only)

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## Non-Negotiables

- docs/V1_CONTRACT.md must not change.
- Tool list (8 tools) must not change.
- Tool schemas must not change.
- Identity rules must not change.
- Merge semantics must not change.

## Guardrail Strategy

1. Golden tests for tool outputs.
2. Schema snapshot tests.
3. CI block on V1_CONTRACT modifications.
4. Intelligence layer must fail-open (never affect tool responses).
