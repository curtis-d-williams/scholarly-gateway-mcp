# Intelligence Layer — Data Model (Design Only)

> Design-only. No impact to V1 contract.
> The V1 contract is frozen at docs/V1_CONTRACT.md.

## Identity

All intelligence tables reference:

- work_key (sha256, defined by V1)
- cluster_key (sha256, defined by V1)

No new identity system is introduced.

## Core Conceptual Tables

### work
- work_key (PK)
- cluster_key
- created_at
- last_seen_at

### citation_edge
- citing_work_key
- cited_work_key
- observed_at
- source_provider

Edges represent provider-asserted citations only. No inferred edges.

### work_metadata_snapshot
- work_key
- observed_at
- source_provider
- title
- authors
- venue
- year
- abstract_hash

Snapshots are append-only.

### fulltext_link_snapshot
- work_key
- observed_at
- source_provider
- link_type
- url

Append-only.
