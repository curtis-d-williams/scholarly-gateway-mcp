# Intelligence Layer — Provenance Ledger (Design Only)

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## Purpose

Record append-only events describing:

- Provider fetches
- Identifier normalization
- Edge observations
- Snapshot creation

Ledger events must never modify V1 behavior.

## Event Structure

- event_id (sha256 of canonical JSON)
- event_type
- observed_at
- source_provider
- work_key (optional)
- payload_json
- payload_hash

## Event Types (Minimal)

- FETCH_WORK
- FETCH_REFERENCES
- FETCH_CITATIONS
- NORMALIZE_IDENTIFIER
- ADD_EDGE
- ADD_METADATA_SNAPSHOT

No behavioral logic is implemented here. Ledger is descriptive only.
