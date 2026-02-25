"""Offline determinism harness — frozen invariants for canonical_json and key derivation.

Validates:
  1) canonical_json() is byte-for-byte stable across repeated calls for a
     representative nested object (sorted keys, compact separators, UTF-8).
  2) generate_work_key() and generate_cluster_key() are stable and
     deterministic for fixed identifier inputs.

No network calls are made; no mocking is required.
"""
from __future__ import annotations

import json

import pytest

from scholarly_gateway.intel_ledger import canonical_json
from scholarly_gateway.identity import generate_cluster_key, generate_work_key


# ---------------------------------------------------------------------------
# canonical_json — byte-for-byte stability
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    """canonical_json must be idempotent and structurally invariant."""

    _REPRESENTATIVE = {
        "z_last": [1, 2, 3],
        "a_first": {"nested_b": False, "nested_a": None},
        "m_middle": "Héllo wörld",
        "num": 42,
    }

    def test_idempotent_repeated_calls(self):
        """Same object → same bytes every call."""
        result1 = canonical_json(self._REPRESENTATIVE)
        result2 = canonical_json(self._REPRESENTATIVE)
        assert result1 == result2

    def test_key_order_is_sorted(self):
        """Keys must be sorted lexicographically at every nesting level."""
        obj = {"z": 1, "a": 2, "m": 3}
        out = canonical_json(obj)
        parsed = json.loads(out)
        assert list(parsed.keys()) == sorted(parsed.keys())

    def test_nested_key_order_is_sorted(self):
        """Nested objects must also have sorted keys."""
        obj = {"outer_z": {"inner_b": 2, "inner_a": 1}, "outer_a": 0}
        out = canonical_json(obj)
        parsed = json.loads(out)
        assert list(parsed.keys()) == sorted(parsed.keys())
        assert list(parsed["outer_z"].keys()) == sorted(parsed["outer_z"].keys())

    def test_compact_separators_no_spaces(self):
        """Output must use compact separators (no spaces after , or :)."""
        obj = {"a": 1, "b": 2}
        out = canonical_json(obj)
        assert ": " not in out
        assert ", " not in out

    def test_utf8_characters_not_escaped(self):
        """Non-ASCII characters must appear as-is (ensure_ascii=False)."""
        obj = {"title": "Héllo wörld 日本語"}
        out = canonical_json(obj)
        assert "Héllo" in out
        assert "日本語" in out
        assert "\\u" not in out

    def test_output_is_valid_json(self):
        """Output must round-trip through json.loads without loss."""
        out = canonical_json(self._REPRESENTATIVE)
        parsed = json.loads(out)
        assert parsed == self._REPRESENTATIVE

    def test_stable_across_different_insertion_orders(self):
        """Two dicts with same content but different insertion order → same bytes."""
        obj_a = {"b": 2, "a": 1, "c": 3}
        obj_b = {"c": 3, "a": 1, "b": 2}
        assert canonical_json(obj_a) == canonical_json(obj_b)

    def test_none_serialised_as_null(self):
        out = canonical_json({"k": None})
        assert out == '{"k":null}'

    def test_bool_serialised_correctly(self):
        assert canonical_json({"t": True, "f": False}) == '{"f":false,"t":true}'

    def test_empty_object(self):
        assert canonical_json({}) == "{}"

    def test_list_order_preserved(self):
        """Lists must preserve insertion order (not sorted)."""
        obj = {"items": [3, 1, 2]}
        out = canonical_json(obj)
        parsed = json.loads(out)
        assert parsed["items"] == [3, 1, 2]


# ---------------------------------------------------------------------------
# Key derivation — stable, deterministic, correct format
# ---------------------------------------------------------------------------

class TestWorkKeyDeterminism:
    """generate_work_key must produce the same key for the same inputs every time."""

    def test_doi_key_stable(self):
        k1, s1 = generate_work_key(doi_norm="10.1038/nature12373")
        k2, s2 = generate_work_key(doi_norm="10.1038/nature12373")
        assert k1 == k2
        assert s1 == s2

    def test_arxiv_key_stable(self):
        k1, _ = generate_work_key(arxiv_id_norm="2101.12345")
        k2, _ = generate_work_key(arxiv_id_norm="2101.12345")
        assert k1 == k2

    def test_weak_fallback_key_stable(self):
        kwargs = dict(title="Attention Is All You Need", first_author="Vaswani", year=2017)
        k1, s1 = generate_work_key(**kwargs)
        k2, s2 = generate_work_key(**kwargs)
        assert k1 == k2
        assert s1 == s2

    def test_doi_key_format(self):
        k, strength = generate_work_key(doi_norm="10.1038/nature12373")
        assert k.startswith("wrk_")
        assert strength == "strong"

    def test_arxiv_key_format(self):
        k, strength = generate_work_key(arxiv_id_norm="2101.12345")
        assert k.startswith("wrk_")
        assert strength == "strong"

    def test_weak_key_format(self):
        k, strength = generate_work_key(title="Some Paper", first_author="Smith", year=2020)
        assert k.startswith("wrk_")
        assert strength == "weak"

    def test_different_dois_produce_different_keys(self):
        k1, _ = generate_work_key(doi_norm="10.1038/nature12373")
        k2, _ = generate_work_key(doi_norm="10.1000/xyz123")
        assert k1 != k2

    def test_doi_takes_priority_over_arxiv(self):
        """When both doi_norm and arxiv_id_norm are supplied, DOI wins."""
        k_doi_only, _ = generate_work_key(doi_norm="10.1038/nature12373")
        k_both, _ = generate_work_key(doi_norm="10.1038/nature12373", arxiv_id_norm="2101.99999")
        assert k_doi_only == k_both

    def test_key_length_consistent(self):
        """All work keys must have the same total length."""
        k_doi, _ = generate_work_key(doi_norm="10.1038/nature12373")
        k_arxiv, _ = generate_work_key(arxiv_id_norm="2101.12345")
        k_weak, _ = generate_work_key(title="T", first_author="A", year=2000)
        assert len(k_doi) == len(k_arxiv) == len(k_weak)


class TestClusterKeyDeterminism:
    """generate_cluster_key must produce the same key for the same inputs every time."""

    def test_doi_cluster_key_stable(self):
        c1, s1 = generate_cluster_key(doi_norm="10.1038/nature12373")
        c2, s2 = generate_cluster_key(doi_norm="10.1038/nature12373")
        assert c1 == c2
        assert s1 == s2

    def test_arxiv_cluster_key_stable(self):
        c1, _ = generate_cluster_key(arxiv_id_norm="2101.12345")
        c2, _ = generate_cluster_key(arxiv_id_norm="2101.12345")
        assert c1 == c2

    def test_cluster_key_format(self):
        c, strength = generate_cluster_key(doi_norm="10.1038/nature12373")
        assert c.startswith("clu_")
        assert strength == "strong"

    def test_cluster_and_work_keys_are_distinct(self):
        """work_key and cluster_key for the same input must differ."""
        k, _ = generate_work_key(doi_norm="10.1038/nature12373")
        c, _ = generate_cluster_key(doi_norm="10.1038/nature12373")
        assert k != c

    def test_cluster_key_same_doi_arxiv_priority(self):
        """DOI takes priority over arXiv for cluster key as well."""
        c_doi_only, _ = generate_cluster_key(doi_norm="10.1038/nature12373")
        c_both, _ = generate_cluster_key(doi_norm="10.1038/nature12373", arxiv_id_norm="2101.99999")
        assert c_doi_only == c_both

    def test_cluster_key_length_consistent(self):
        c_doi, _ = generate_cluster_key(doi_norm="10.1038/nature12373")
        c_arxiv, _ = generate_cluster_key(arxiv_id_norm="2101.12345")
        c_weak, _ = generate_cluster_key(title="T", first_author="A", year=2000)
        assert len(c_doi) == len(c_arxiv) == len(c_weak)
