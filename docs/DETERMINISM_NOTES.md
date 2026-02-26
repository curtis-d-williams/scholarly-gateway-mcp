# Determinism Notes — V1 Contract

This document clarifies what “deterministic” means within
`scholarly-gateway-mcp` and what it does not mean.

The V1 contract is frozen. Behavior described here must not change
without an explicit contract revision.

---

## 1. Deterministic Scope

The gateway guarantees determinism at the **gateway layer**, not at the provider layer.

Deterministic components:

- Tool names
- Tool parameters
- Output schema structure
- Field names
- Response shape
- Error envelope format
- `provider_status` structure
- Fail-closed behavior when providers are unavailable or unsupported

Given identical inputs and identical upstream provider responses,
the gateway will produce identical outputs.

---

## 2. Provider Variability (Non-Deterministic Boundary)

Upstream providers (e.g., arXiv, OpenAlex) may change:

- Ranking behavior
- Metadata normalization
- API response shape
- Availability
- Latency
- HTTP status behavior

The gateway does **not** attempt to override or reinterpret provider data
beyond minimal normalization required for schema stability.

Therefore:

- Result ordering may change if the provider changes.
- Metadata fields may differ if the provider changes.
- Availability depends on upstream services.

This is why `provider_status` is included in every response.

---

## 3. provider_status as a Reproducibility Primitive

Every tool response includes:

- Provider name
- Status
- HTTP code (when applicable)
- Error classification (if any)

This allows bug reports to distinguish:

- Gateway logic errors
- Provider unavailability
- Provider contract changes
- Unsupported provider usage

Deterministic systems require deterministic reproduction.
`provider_status` is the minimum reproducibility surface.

---

## 4. Fail-Closed Behavior

The gateway fails closed when:

- A requested provider is unsupported
- A provider returns a non-success status
- Required parameters are missing
- Input schema is invalid

The gateway does not silently substitute providers.
The gateway does not silently retry across providers unless explicitly requested.

Explicit provider selection is preserved.

---

## 5. What This System Does Not Do

The gateway does not:

- Cache or rank across providers
- Merge semantic results across heterogeneous sources
- Perform heuristic reconciliation
- Infer intent beyond explicit parameters
- Modify upstream metadata beyond schema alignment
- Provide scoring, ranking, or policy inference

This is a substrate, not an opinionated research engine.

---

## 6. Versioning Discipline

- V1 contract is frozen.
- Tool surface changes require explicit contract revision.
- Metadata-only releases (e.g., 0.2.2) must not alter behavior.
- Deterministic guarantees apply across patch releases.

If behavior changes, the contract must change.

---

## 7. Reproducibility Checklist

For deterministic reproduction, capture:

- scholarly-gateway-mcp version
- OS + Python version
- MCP client name + version
- Tool name invoked
- Exact JSON payload
- Full `provider_status`
- Timestamp (recommended)

Without this information, bugs are not reproducible.

---

## Summary

Determinism in this system means:

- Stable interface
- Stable schema
- Stable failure semantics

It does not mean:

- Stable upstream provider behavior

The gateway enforces contract discipline.
Upstream variability is made visible, not hidden.
