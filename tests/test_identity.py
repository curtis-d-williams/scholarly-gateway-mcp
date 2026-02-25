"""Tests for identity normalization, keying, and merge/link logic.

Mandatory per V1 contract section 10:
  1) DOI normalization
  2) arXiv ID/version parsing
  3) hard-merge behavior on DOI
  4) "no merge" on similarity-only
  5) stable work_key determinism
"""
import pytest

from scholarly_gateway.identity import (
    can_hard_merge,
    generate_cluster_key,
    generate_work_key,
    hard_merge,
    normalize_arxiv_id,
    normalize_doi,
    soft_link,
)
from scholarly_gateway.models import (
    Bibliographic,
    Identifiers,
    InternalWork,
    Provenance,
    ProvenanceRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_work(
    doi=None,
    arxiv_id=None,
    openalex_id=None,
    title="Test Paper",
    author="A. Author",
    year=2021,
    provider="openalex",
) -> InternalWork:
    work_key, key_strength = generate_work_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id,
        title=title,
        first_author=author,
        year=year,
    )
    cluster_key, _ = generate_cluster_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id,
        title=title,
        first_author=author,
        year=year,
    )
    return InternalWork(
        work_key=work_key,
        cluster_key=cluster_key,
        key_strength=key_strength,
        bibliographic=Bibliographic(
            title=title,
            authors_preview=[author],
            publication_year=year,
        ),
        identifiers=Identifiers(doi=doi, arxiv_id=arxiv_id, openalex_id=openalex_id),
        provenance=Provenance(records=[
            ProvenanceRecord(
                provider=provider,
                record_id=doi or arxiv_id or openalex_id or "test",
                fetched_at="2024-01-01T00:00:00+00:00",
            )
        ]),
    )


# ---------------------------------------------------------------------------
# 1) DOI normalization
# ---------------------------------------------------------------------------

class TestDoiNormalization:
    def test_strips_https_resolver(self):
        assert normalize_doi("https://doi.org/10.1038/nature12373") == "10.1038/nature12373"

    def test_strips_http_resolver(self):
        assert normalize_doi("http://doi.org/10.1038/nature12373") == "10.1038/nature12373"

    def test_strips_dx_resolver(self):
        assert normalize_doi("https://dx.doi.org/10.1000/xyz123") == "10.1000/xyz123"

    def test_strips_doi_prefix(self):
        assert normalize_doi("doi:10.1000/xyz123") == "10.1000/xyz123"

    def test_lowercases(self):
        assert normalize_doi("10.1000/XYZ123") == "10.1000/xyz123"

    def test_strips_whitespace(self):
        assert normalize_doi("  10.1000/xyz123  ") == "10.1000/xyz123"

    def test_none_input(self):
        assert normalize_doi(None) is None

    def test_empty_string(self):
        assert normalize_doi("") is None

    def test_bare_doi_unchanged(self):
        assert normalize_doi("10.1038/nature12373") == "10.1038/nature12373"


# ---------------------------------------------------------------------------
# 2) arXiv ID / version parsing
# ---------------------------------------------------------------------------

class TestArxivIdNormalization:
    def test_new_style_bare(self):
        arxiv_id, version = normalize_arxiv_id("2101.12345")
        assert arxiv_id == "2101.12345"
        assert version is None

    def test_new_style_with_version(self):
        arxiv_id, version = normalize_arxiv_id("2101.12345v3")
        assert arxiv_id == "2101.12345"
        assert version == "v3"

    def test_strips_abs_url(self):
        arxiv_id, version = normalize_arxiv_id("https://arxiv.org/abs/2101.12345v2")
        assert arxiv_id == "2101.12345"
        assert version == "v2"

    def test_strips_pdf_url(self):
        arxiv_id, version = normalize_arxiv_id("https://arxiv.org/pdf/2101.12345v1")
        assert arxiv_id == "2101.12345"
        assert version == "v1"

    def test_old_style(self):
        arxiv_id, version = normalize_arxiv_id("hep-th/9901001")
        assert arxiv_id == "hep-th/9901001"
        assert version is None

    def test_old_style_with_version(self):
        arxiv_id, version = normalize_arxiv_id("hep-th/9901001v2")
        assert arxiv_id == "hep-th/9901001"
        assert version == "v2"

    def test_strips_arxiv_prefix(self):
        arxiv_id, version = normalize_arxiv_id("arxiv:2101.12345")
        assert arxiv_id == "2101.12345"

    def test_none_input(self):
        arxiv_id, version = normalize_arxiv_id(None)
        assert arxiv_id is None
        assert version is None

    def test_invalid_returns_none(self):
        arxiv_id, version = normalize_arxiv_id("not-an-id")
        assert arxiv_id is None


# ---------------------------------------------------------------------------
# 3) Hard-merge behavior on DOI
# ---------------------------------------------------------------------------

class TestHardMerge:
    def test_merges_on_shared_doi(self):
        a = _make_work(doi="10.1038/nature12373", provider="openalex")
        b = _make_work(doi="10.1038/nature12373", provider="arxiv")
        assert can_hard_merge(a, b) is True

    def test_merge_combines_provenance(self):
        a = _make_work(doi="10.1038/nature12373", provider="openalex")
        b = _make_work(doi="10.1038/nature12373", provider="arxiv", arxiv_id="2101.12345")
        merged = hard_merge(a, b)
        providers = {r.provider for r in merged.provenance.records}
        assert "openalex" in providers
        assert "arxiv" in providers

    def test_merge_fills_missing_arxiv_id(self):
        a = _make_work(doi="10.1038/nature12373", provider="openalex")
        b = _make_work(doi="10.1038/nature12373", arxiv_id="2101.12345", provider="arxiv")
        merged = hard_merge(a, b)
        assert merged.identifiers.arxiv_id == "2101.12345"

    def test_merges_on_shared_arxiv_id(self):
        a = _make_work(arxiv_id="2101.12345", provider="arxiv")
        b = _make_work(arxiv_id="2101.12345", provider="openalex")
        assert can_hard_merge(a, b) is True

    def test_no_merge_on_different_doi(self):
        a = _make_work(doi="10.1038/nature12373")
        b = _make_work(doi="10.1000/xyz123")
        assert can_hard_merge(a, b) is False


# ---------------------------------------------------------------------------
# 4) No merge on similarity-only (different IDs)
# ---------------------------------------------------------------------------

class TestNoMergeOnSimilarity:
    def test_same_title_different_ids_not_hard_merged(self):
        a = _make_work(doi="10.1000/aaa", title="Attention Is All You Need")
        b = _make_work(doi="10.1000/bbb", title="Attention Is All You Need")
        assert can_hard_merge(a, b) is False

    def test_same_title_no_ids_not_hard_merged(self):
        a = _make_work(title="Attention Is All You Need", year=2017)
        b = _make_work(title="Attention Is All You Need", year=2017)
        # They have no shared hard identifier (and weak keys may collide — that's OK
        # per the fallback spec — but can_hard_merge checks identifiers only)
        assert can_hard_merge(a, b) is False

    def test_soft_link_added_for_same_title(self):
        a = _make_work(doi="10.1000/aaa", title="Attention Is All You Need", year=2017)
        b = _make_work(doi="10.1000/bbb", title="Attention Is All You Need", year=2017)
        linked = soft_link([a, b])
        # Both should have linked_candidates pointing to the other
        assert len(linked[0].linked_candidates) >= 1
        assert linked[0].linked_candidates[0].work_key == b.work_key
        assert linked[1].linked_candidates[0].work_key == a.work_key

    def test_soft_link_does_not_collapse(self):
        a = _make_work(doi="10.1000/aaa", title="Attention Is All You Need", year=2017)
        b = _make_work(doi="10.1000/bbb", title="Attention Is All You Need", year=2017)
        linked = soft_link([a, b])
        # Still two separate works
        assert len(linked) == 2


# ---------------------------------------------------------------------------
# 5) Stable work_key determinism
# ---------------------------------------------------------------------------

class TestWorkKeyDeterminism:
    def test_doi_key_is_stable(self):
        k1, _ = generate_work_key(doi_norm="10.1038/nature12373")
        k2, _ = generate_work_key(doi_norm="10.1038/nature12373")
        assert k1 == k2

    def test_arxiv_key_is_stable(self):
        k1, _ = generate_work_key(arxiv_id_norm="2101.12345")
        k2, _ = generate_work_key(arxiv_id_norm="2101.12345")
        assert k1 == k2

    def test_doi_key_starts_with_wrk(self):
        k, _ = generate_work_key(doi_norm="10.1038/nature12373")
        assert k.startswith("wrk_")

    def test_different_dois_produce_different_keys(self):
        k1, _ = generate_work_key(doi_norm="10.1038/nature12373")
        k2, _ = generate_work_key(doi_norm="10.1000/xyz123")
        assert k1 != k2

    def test_doi_key_strength_is_strong(self):
        _, strength = generate_work_key(doi_norm="10.1038/nature12373")
        assert strength == "strong"

    def test_fallback_key_strength_is_weak(self):
        _, strength = generate_work_key(title="Some Title", first_author="A. Author", year=2021)
        assert strength == "weak"

    def test_cluster_key_stable_for_doi(self):
        c1, _ = generate_cluster_key(doi_norm="10.1038/nature12373")
        c2, _ = generate_cluster_key(doi_norm="10.1038/nature12373")
        assert c1 == c2
        assert c1.startswith("clu_")
