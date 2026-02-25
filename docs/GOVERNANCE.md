# Governance

## Authority model

| Role | Authority |
|---|---|
| Curtis (Product Owner) | Final authority on all design decisions, contract changes, and release approvals. |
| Architect/Reviewer | Produces specs, review checklists, and architectural assessments. No unilateral authority to merge or release. |
| Executor (Claude Code) | Implements exactly what the spec states. No design authority. Cannot approve its own changes. |

Executors implement; they do not decide. Any executor that expands scope beyond a written, approved spec is acting outside its authority. Such changes must not be merged.

---

## Change control

### What is frozen

| Artifact | Frozen since | Rule |
|---|---|---|
| `docs/V1_CONTRACT.md` | v0.1.3 | Immutable without explicit Product Owner decision. No PRs modify this file without approval. |
| Tool schemas (all 7 tools) | v0.1.3 | Field names, types, and semantics are frozen. |
| IDO schema (`schema_version: "1.0"`) | v0.1.3 | No field additions, removals, or type changes. |
| Identifier formats (`work_key`, `cluster_key`, `doi_norm`, `arxiv_id_norm`) | v0.1.3 | Computation must not change. Existing keys must remain valid. |
| Merge/identity policy (§3 of contract) | v0.1.3 | Hard merge and soft link rules are frozen. |
| Ledger Phase 1 invariants (I1–I5) | 2026-02-25 | Frozen per `docs/LEDGER_PHASE1.md`. New event types and schema changes require Phase 2 decision. |
| `canonical_json` serialization | v0.1.3 | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` is fixed. |

### What can evolve without a contract revision

- Documentation, examples, troubleshooting guides.
- Internal implementation details that do not alter any observable tool output.
- Test coverage expansion (adding tests, not removing).
- Typo fixes in non-normative text.

### How to reopen a frozen artifact

1. Identify the specific contract item that needs to change and state the reason precisely.
2. File an issue or bring the change to the Product Owner directly.
3. The Product Owner issues an explicit written decision (approval or rejection).
4. If approved: create a new or updated spec document, reviewed by the architect.
5. Only after the spec is approved may implementation begin.

Absence of an explicit approval decision means the freeze holds.

---

## Versioning doctrine

This project follows [Semantic Versioning](https://semver.org/) with the following interpretations:

| Change type | Version bump |
|---|---|
| Any change to a frozen contract artifact (tool schema, IDO, identifier format, merge policy) | **Major** (`X.0.0`) |
| New tool or new required output field | **Major** (`X.0.0`) |
| New optional output field in an existing tool (additive, non-breaking) | **Minor** (`0.X.0`) |
| New provider added (additive, existing tools) | **Minor** (`0.X.0`) |
| Bug fix with no observable contract change | **Patch** (`0.0.X`) |
| Documentation-only change | **Patch** (`0.0.X`) |
| Internal refactor with identical observable outputs | **Patch** (`0.0.X`) |

**Current stable version:** v0.1.3 (behavior frozen).

A "non-breaking" additive change that is visible to callers (new field, new tool) is still a **minor** bump because callers may need to handle it.

---

## Compatibility posture

- **Contract-first.** The tool surface and IDO schema defined in `docs/V1_CONTRACT.md` are the normative interface. Implementation follows the contract; the contract does not follow the implementation.
- **Examples are non-normative.** `docs/EXAMPLES.md` illustrates expected behavior but does not define it. In any conflict, `docs/V1_CONTRACT.md` is authoritative.
- **Callers may rely on frozen fields.** Any field present in a V1 tool output that is defined in the contract will not be removed or renamed in a patch or minor release.
- **Callers must not rely on undocumented fields.** Fields not defined in `docs/V1_CONTRACT.md` are internal and may be removed without notice.

---

## Release checklist

### Docs-only release (patch bump)

- [ ] All changed files are `.md` only.
- [ ] No normative contract claims have been altered.
- [ ] `pytest -q` passes unchanged.
- [ ] Product Owner approves PR.
- [ ] Tag `v0.0.X` after merge.

### Code release (patch, minor, or major)

- [ ] All new or changed behavior is covered by the spec.
- [ ] `pytest -q` passes with no new failures.
- [ ] Frozen artifacts are unchanged (or a contract revision has been explicitly approved).
- [ ] Changelog entry written.
- [ ] Product Owner approves PR.
- [ ] Architect has reviewed any schema or contract-adjacent changes.
- [ ] Tag `vX.Y.Z` after merge.
- [ ] PyPI publish follows `docs/PYPI_PUBLISHING.md`.
