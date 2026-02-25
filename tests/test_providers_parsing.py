"""Tests for provider parsing using static fixture files."""
from __future__ import annotations

import json
import pathlib
import xml.etree.ElementTree as ET

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# OpenAlex parsing
# ---------------------------------------------------------------------------

class TestOpenAlexParsing:
    def _load_fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    def _parse(self, raw: dict):
        from scholarly_gateway.providers.openalex import _parse_work
        return _parse_work(raw)

    def test_work_with_doi(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert work.identifiers.doi == "10.1038/nature12373"
        assert work.bibliographic.title == "Human-level control through deep reinforcement learning"
        assert work.bibliographic.publication_year == 2015
        assert work.key_strength == "strong"
        assert work.work_key.startswith("wrk_")

    def test_work_with_doi_is_journal_article(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert work.kind == "journal-article"
        assert work.status.review_status == "peer-reviewed"

    def test_work_with_doi_has_oa_info(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert work.access.is_open_access is True
        assert work.access.best_oa_url is not None

    def test_work_with_doi_reconstructs_abstract(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert work.abstract.teaser is not None
        assert len(work.abstract.teaser) > 0

    def test_work_without_doi(self):
        raw = self._load_fixture("openalex_work_without_doi.json")
        work = self._parse(raw)
        assert work.identifiers.doi is None
        assert work.identifiers.openalex_id == "https://openalex.org/W9999999999"

    def test_work_without_doi_key_strength(self):
        raw = self._load_fixture("openalex_work_without_doi.json")
        work = self._parse(raw)
        # No DOI, no arXiv ID → key based on openalex_id fallback via weak
        # (openalex_id is not a hard-key input to generate_work_key — it's a fallback)
        assert work.work_key.startswith("wrk_")

    def test_work_without_doi_is_preprint(self):
        raw = self._load_fixture("openalex_work_without_doi.json")
        work = self._parse(raw)
        assert work.kind == "preprint"
        assert work.status.review_status == "preprint"

    def test_provenance_record(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert len(work.provenance.records) == 1
        assert work.provenance.records[0].provider == "openalex"
        assert work.provenance.records[0].record_id == "https://openalex.org/W2741809807"

    def test_authors_preview_max_3(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert len(work.bibliographic.authors_preview) <= 3

    def test_metrics_cited_by_count(self):
        raw = self._load_fixture("openalex_work_with_doi.json")
        work = self._parse(raw)
        assert work.metrics_preview.cited_by_count == 22000


# ---------------------------------------------------------------------------
# arXiv parsing
# ---------------------------------------------------------------------------

class TestArxivParsing:
    def _load_fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text()

    def _parse_feed(self, xml_text: str):
        from scholarly_gateway.providers.arxiv import _parse_feed
        return _parse_feed(xml_text)

    def test_entry_with_doi(self):
        xml = self._load_fixture("arxiv_entry_with_doi.xml")
        works = self._parse_feed(xml)
        assert len(works) == 1
        w = works[0]
        assert w.identifiers.arxiv_id == "1312.6114"
        assert w.identifiers.doi == "10.48550/arxiv.1312.6114"
        assert w.bibliographic.title == "Auto-Encoding Variational Bayes"

    def test_entry_with_doi_key_strength_strong(self):
        xml = self._load_fixture("arxiv_entry_with_doi.xml")
        works = self._parse_feed(xml)
        assert works[0].key_strength == "strong"

    def test_entry_with_doi_review_status(self):
        xml = self._load_fixture("arxiv_entry_with_doi.xml")
        works = self._parse_feed(xml)
        # Has journal_ref so should be peer-reviewed
        assert works[0].status.review_status == "peer-reviewed"

    def test_entry_with_doi_is_oa(self):
        xml = self._load_fixture("arxiv_entry_with_doi.xml")
        works = self._parse_feed(xml)
        assert works[0].access.is_open_access is True

    def test_entry_without_doi(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        assert len(works) == 1
        w = works[0]
        assert w.identifiers.arxiv_id == "2101.12345"
        assert w.identifiers.doi is None

    def test_entry_without_doi_key_is_strong_via_arxiv(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        # Has arXiv ID → strong key
        assert works[0].key_strength == "strong"

    def test_entry_without_doi_is_preprint(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        assert works[0].status.review_status == "preprint"
        assert works[0].kind == "preprint"

    def test_entry_has_abstract(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        assert works[0].abstract.teaser is not None
        assert "graph" in works[0].abstract.teaser.lower()

    def test_entry_has_links(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        w = works[0]
        assert w.links.arxiv_abs_url is not None
        assert "2101.12345" in w.links.arxiv_abs_url

    def test_entry_provenance(self):
        xml = self._load_fixture("arxiv_entry_without_doi.xml")
        works = self._parse_feed(xml)
        assert works[0].provenance.records[0].provider == "arxiv"

    def test_authors_preview_max_3(self):
        xml = self._load_fixture("arxiv_entry_with_doi.xml")
        works = self._parse_feed(xml)
        assert len(works[0].bibliographic.authors_preview) <= 3


# ---------------------------------------------------------------------------
# Integration: merge works from both providers
# ---------------------------------------------------------------------------

class TestMergeIntegration:
    def test_doi_match_merges_openalex_and_arxiv(self):
        """When OpenAlex and arXiv records share a DOI, they hard-merge."""
        from scholarly_gateway.identity import merge_work_lists
        from scholarly_gateway.providers.openalex import _parse_work as oa_parse
        from scholarly_gateway.providers.arxiv import _parse_feed as ax_parse

        # Use the with-DOI fixtures — they share doi 10.1038/nature12373 / 10.48550/arxiv.1312.6114
        # (different DOIs in test fixtures, so we manually construct a matching pair)
        from scholarly_gateway.identity import generate_work_key, generate_cluster_key, normalize_doi
        from scholarly_gateway.models import (
            Bibliographic, Identifiers, InternalWork, Provenance, ProvenanceRecord
        )

        doi = "10.1038/nature12373"
        wk, ks = generate_work_key(doi_norm=doi)
        ck, _ = generate_cluster_key(doi_norm=doi)

        oa_work = InternalWork(
            work_key=wk, cluster_key=ck, key_strength=ks,
            bibliographic=Bibliographic(title="DQN Paper", publication_year=2015),
            identifiers=Identifiers(doi=doi, openalex_id="https://openalex.org/W1"),
            provenance=Provenance(records=[ProvenanceRecord(
                provider="openalex", record_id="W1", fetched_at="2024-01-01T00:00:00+00:00")])
        )
        ax_work = InternalWork(
            work_key=wk, cluster_key=ck, key_strength=ks,
            bibliographic=Bibliographic(title="DQN Paper", publication_year=2015),
            identifiers=Identifiers(doi=doi, arxiv_id="1312.5602"),
            provenance=Provenance(records=[ProvenanceRecord(
                provider="arxiv", record_id="1312.5602", fetched_at="2024-01-01T00:00:00+00:00")])
        )

        merged = merge_work_lists([[oa_work], [ax_work]])
        assert len(merged) == 1
        result = merged[0]
        assert result.identifiers.doi == doi
        assert result.identifiers.arxiv_id == "1312.5602"
        assert result.identifiers.openalex_id == "https://openalex.org/W1"
        providers_in_provenance = {r.provider for r in result.provenance.records}
        assert providers_in_provenance == {"openalex", "arxiv"}
