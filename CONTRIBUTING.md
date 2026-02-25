# Contributing to scholarly-gateway-mcp

## Project intent

This project is deterministic, provenance-aware infrastructure for scholarly data access. It is contract-driven: the V1 tool surface and IDO schema are the authoritative interface, and correctness is defined by reproducible, auditable outputs — not by utility heuristics or feature richness.

The goal is a stable, trustworthy gateway that agents and humans can rely on across sessions. Stability and determinism take precedence over new capability.

---

## Running tests and local checks

All commands use the existing toolchain. Do not introduce new build tools, scripts, or runners.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Verify the server starts:

```
scholarly-gateway
```

There are no other required local checks beyond `pytest -q` and a clean server start.

---

## PR types and what is allowed

### Docs-only PRs

Changes limited to `.md` files (docs/, README.md, CONTRIBUTING.md, etc.) and no source code.

- Allowed: clarifications, examples, governance updates, typo fixes, new documentation files.
- Must not alter tool schemas, IDO schema, identifier formats, merge policy, or any behavioral contract.
- Must not make normative claims that conflict with `docs/V1_CONTRACT.md`.

### Code PRs

Changes to any `.py` file, `pyproject.toml`, test fixtures, or configuration.

- Not accepted without explicit Product Owner approval and an architecture review.
- Must include corresponding test coverage.
- Must not expand the tool surface, add dependencies, or alter frozen contracts (see below).
- Must pass `pytest -q` with no new failures.

---

## Determinism rules

Every tool output must be deterministic given the same inputs. Specifically:

- `work_key` and `cluster_key` are stable hashes; their computation must not change.
- `canonical_json` serialization is frozen; do not alter `json.dumps` arguments.
- No random, time-dependent, or process-dependent values may appear in tool outputs.
- No hidden state dependence: tool outputs must not vary based on prior calls, session order, or ambient environment beyond explicit configuration.
- The ledger (if enabled) is write-only infrastructure; it must not influence any tool output.

Any code change that introduces nondeterminism in tool outputs is a contract violation and will not be merged.

---

## Contract rule

The V1 contract (`docs/V1_CONTRACT.md`) is frozen.

- Do not propose changes to tool schemas, IDO fields, identifier formats, merge policy, pagination behavior, provider_status values, or error envelopes.
- Do not open PRs that modify `docs/V1_CONTRACT.md`.
- If a genuine contract issue is identified (e.g., ambiguity causing incompatible interpretations), file an issue describing the problem precisely. Reopening the contract requires an explicit decision by the Product Owner; it is not the default outcome.

---

## How to propose new tools or features

The default answer to new tools and features is **no**.

New tools or features require:

1. A written architectural justification explaining why the addition cannot be deferred.
2. Explicit Product Owner approval before any code is written.
3. A contract addendum or new spec document reviewed by the architect.
4. Test coverage that verifies the new contract properties.

Do not open PRs implementing new functionality without prior written approval. Implementation work without approval will be closed without review.

---

## Style

- Write precisely. Avoid marketing language, hype, and vague qualitative claims.
- Documentation should state what the system does, what it guarantees, and what it explicitly does not do.
- Error conditions and partial results are first-class; document them.
- Examples are non-normative. The contract documents are authoritative.
