"""Freeze the JSON-schema "spine" for V1 contract-bound output models.

If any field name, type annotation, or required/optional status changes in a
contract model the sha256 digest of its canonical JSON schema will diverge from
the constant stored here, causing this test to fail with a clear diagnostic.

Digests were generated in-process at authoring time with:

    hashlib.sha256(canonical_json(Model.model_json_schema()).encode()).hexdigest()
"""
from __future__ import annotations

import hashlib

import pytest

from scholarly_gateway.intel_ledger import canonical_json
from scholarly_gateway.models import (
    CitationsOutput,
    GetWorkOutput,
    InternalWork,
    ProviderStatus,
    SearchWorksOutput,
)

# ---------------------------------------------------------------------------
# Baked-in expected digests — update only via intentional contract change.
# ---------------------------------------------------------------------------

_EXPECTED: dict[str, str] = {
    "CitationsOutput": "663d7f1e7843c2fec5e3bac94874e597d8fe89da78f26a42e065251742eff546",
    "GetWorkOutput": "ce77436c762bffaa0c697eeb30ba5a2e9d1dd740ebcd5701a56c6dfcf028591b",
    "InternalWork": "3da037564de8a2a98cf250a3be3b2494a2633614dabd0eb6cd206f45611c1c25",
    "ProviderStatus": "8e6304e4c28e87e63535ec94324f4bc84e61e3ad57491ff00c790ac94ee96204",
    "SearchWorksOutput": "3159f56d7a74fcb51e857596b16159f6b5b5111ffd52e463f95cc71bcc8f3fc1",
}

_MODELS = {
    "CitationsOutput": CitationsOutput,
    "GetWorkOutput": GetWorkOutput,
    "InternalWork": InternalWork,
    "ProviderStatus": ProviderStatus,
    "SearchWorksOutput": SearchWorksOutput,
}


@pytest.mark.parametrize("name", sorted(_MODELS))
def test_schema_digest_unchanged(name: str) -> None:
    model = _MODELS[name]
    schema = model.model_json_schema()
    canon = canonical_json(schema)
    actual = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    expected = _EXPECTED[name]
    assert actual == expected, (
        f"Schema drift detected for model '{name}'.\n"
        f"  expected digest: {expected}\n"
        f"  actual digest:   {actual}\n"
        "Update _EXPECTED only after an intentional, reviewed contract change."
    )
