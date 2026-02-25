"""T3 — Golden Output Tests (contract output equality)
T4 — Determinism Tests (same input twice, same output)

Golden files live in tests/golden/<tool>/<case>.json.
They are auto-created on first run; subsequent runs compare byte-exactly.

No live network calls are made: provider functions are stubbed via monkeypatch.
All timestamps are pinned via _now_iso monkeypatching so outputs are
fully deterministic across runs.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from scholarly_gateway.models import ProviderStatus
from scholarly_gateway.providers.arxiv import _parse_feed as ax_parse_feed
from scholarly_gateway.providers.openalex import _parse_work as oa_parse_work

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"

# Pinned timestamp replaces _now_iso() in both provider modules.
FIXED_TIMESTAMP = "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------

def canonical(obj) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8 safe."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Golden file helpers
# ---------------------------------------------------------------------------

def _save_golden(tool_name: str, case_name: str, text: str) -> None:
    path = GOLDEN_DIR / tool_name / f"{case_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _assert_matches_golden(tool_name: str, case_name: str, output: dict) -> None:
    """Compare output to committed golden (byte-equal canonical JSON).

    Creates the golden file on first run so it can be committed.
    """
    path = GOLDEN_DIR / tool_name / f"{case_name}.json"
    actual = canonical(output)
    if not path.exists():
        _save_golden(tool_name, case_name, actual)
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Golden mismatch for {tool_name}/{case_name}.\n"
        f"  expected (first 300): {expected[:300]!r}\n"
        f"  actual   (first 300): {actual[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Fixture builders — parse static files with pinned fetched_at
# ---------------------------------------------------------------------------

def _build_vit_work(monkeypatch):
    """Parse tests/fixtures/arxiv_2010.11929.xml with fixed fetched_at."""
    import scholarly_gateway.providers.arxiv as arxiv_mod
    monkeypatch.setattr(arxiv_mod, "_now_iso", lambda: FIXED_TIMESTAMP)
    xml = (FIXTURES / "arxiv_2010.11929.xml").read_text(encoding="utf-8")
    works = ax_parse_feed(xml)
    assert len(works) == 1, "arxiv_2010.11929.xml must contain exactly one entry"
    return works[0]


def _build_dqn_work(monkeypatch):
    """Parse tests/fixtures/openalex_work_with_doi.json with fixed fetched_at."""
    import scholarly_gateway.providers.openalex as openalex_mod
    monkeypatch.setattr(openalex_mod, "_now_iso", lambda: FIXED_TIMESTAMP)
    raw = json.loads(
        (FIXTURES / "openalex_work_with_doi.json").read_text(encoding="utf-8")
    )
    return oa_parse_work(raw)


def _build_citation_works(monkeypatch):
    """Parse tests/fixtures/openalex_citations_dqn.json with fixed fetched_at."""
    import scholarly_gateway.providers.openalex as openalex_mod
    monkeypatch.setattr(openalex_mod, "_now_iso", lambda: FIXED_TIMESTAMP)
    raw_list = json.loads(
        (FIXTURES / "openalex_citations_dqn.json").read_text(encoding="utf-8")
    )
    return [oa_parse_work(r) for r in raw_list]


# ---------------------------------------------------------------------------
# T3 — Golden Output Tests
# ---------------------------------------------------------------------------

class TestT3GoldenOutput:
    """T3: tool outputs match committed golden files exactly (canonical JSON)."""

    def test_search_works_arxiv_id_lookup(self, monkeypatch):
        """search_works: query='id:2010.11929', arxiv provider only, no network."""
        vit_work = _build_vit_work(monkeypatch)

        from scholarly_gateway import server
        server._WORK_CACHE.clear()

        async def _stub_arxiv_search(query, filters, sort="relevance", limit=10, start=0):
            return ([vit_work], None, ProviderStatus(status="ok", http_status=200))

        import scholarly_gateway.providers.arxiv as arxiv_mod
        monkeypatch.setattr(arxiv_mod, "search", _stub_arxiv_search)

        result = asyncio.run(
            server.search_works(query="id:2010.11929", providers=["arxiv"])
        )
        _assert_matches_golden("search_works", "arxiv_id_lookup", result)

    def test_get_work_doi_lookup(self, monkeypatch):
        """get_work: DQN paper via work_key injected into cache, no network."""
        dqn_work = _build_dqn_work(monkeypatch)

        from scholarly_gateway import server
        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work

        result = asyncio.run(server.get_work(work_key=dqn_work.work_key))
        _assert_matches_golden("get_work", "doi_lookup", result)

    def test_forward_citations_small_graph(self, monkeypatch):
        """forward_citations: DQN paper → 2 citing works via stub, no network."""
        import scholarly_gateway.providers.openalex as openalex_mod
        dqn_work = _build_dqn_work(monkeypatch)
        citing_works = _build_citation_works(monkeypatch)

        from scholarly_gateway import server
        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work

        async def _stub_fetch_citations(openalex_id, limit=10, cursor=None):
            return (citing_works, None, ProviderStatus(status="ok", http_status=200))

        monkeypatch.setattr(openalex_mod, "fetch_citations", _stub_fetch_citations)

        result = asyncio.run(
            server.forward_citations(work_key=dqn_work.work_key)
        )
        _assert_matches_golden("forward_citations", "small_graph", result)


# ---------------------------------------------------------------------------
# T4 — Determinism Tests
# ---------------------------------------------------------------------------

class TestT4Determinism:
    """T4: running each case twice with identical stubs → byte-equal canonical JSON."""

    def test_search_works_arxiv_id_determinism(self, monkeypatch):
        """search_works: two sequential calls → canonical JSON identical."""
        vit_work = _build_vit_work(monkeypatch)

        import scholarly_gateway.providers.arxiv as arxiv_mod

        async def _stub_arxiv_search(query, filters, sort="relevance", limit=10, start=0):
            return ([vit_work], None, ProviderStatus(status="ok", http_status=200))

        monkeypatch.setattr(arxiv_mod, "search", _stub_arxiv_search)

        from scholarly_gateway import server

        server._WORK_CACHE.clear()
        result1 = asyncio.run(
            server.search_works(query="id:2010.11929", providers=["arxiv"])
        )
        server._WORK_CACHE.clear()
        result2 = asyncio.run(
            server.search_works(query="id:2010.11929", providers=["arxiv"])
        )

        assert canonical(result1) == canonical(result2), (
            "search_works produced different output on second call"
        )

    def test_get_work_doi_determinism(self, monkeypatch):
        """get_work: two sequential cache-hits → canonical JSON identical."""
        dqn_work = _build_dqn_work(monkeypatch)

        from scholarly_gateway import server

        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work
        result1 = asyncio.run(server.get_work(work_key=dqn_work.work_key))

        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work
        result2 = asyncio.run(server.get_work(work_key=dqn_work.work_key))

        assert canonical(result1) == canonical(result2), (
            "get_work produced different output on second call"
        )

    def test_forward_citations_determinism(self, monkeypatch):
        """forward_citations: two sequential stub calls → canonical JSON identical."""
        import scholarly_gateway.providers.openalex as openalex_mod
        dqn_work = _build_dqn_work(monkeypatch)
        citing_works = _build_citation_works(monkeypatch)

        async def _stub_fetch_citations(openalex_id, limit=10, cursor=None):
            return (citing_works, None, ProviderStatus(status="ok", http_status=200))

        monkeypatch.setattr(openalex_mod, "fetch_citations", _stub_fetch_citations)

        from scholarly_gateway import server

        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work
        result1 = asyncio.run(server.forward_citations(work_key=dqn_work.work_key))

        server._WORK_CACHE.clear()
        server._WORK_CACHE[dqn_work.work_key] = dqn_work
        result2 = asyncio.run(server.forward_citations(work_key=dqn_work.work_key))

        assert canonical(result1) == canonical(result2), (
            "forward_citations produced different output on second call"
        )
