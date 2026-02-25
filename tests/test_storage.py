"""Tests for SQLite storage layer and server DB fallback."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from scholarly_gateway.identity import generate_cluster_key, generate_work_key
from scholarly_gateway.models import (
    Bibliographic,
    Identifiers,
    InternalWork,
    Provenance,
    ProvenanceRecord,
    ProviderStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_work(
    doi: str | None = None,
    arxiv_id: str | None = None,
    openalex_id: str | None = None,
    title: str = "Test Paper",
    author: str = "A. Author",
    year: int = 2021,
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
        provenance=Provenance(
            records=[
                ProvenanceRecord(
                    provider="openalex",
                    record_id=openalex_id or doi or arxiv_id or "test",
                    fetched_at="2024-01-01T00:00:00+00:00",
                )
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Storage unit tests
# ---------------------------------------------------------------------------

class TestStorageRoundtrip:
    def test_upsert_and_get_with_all_identifiers(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import get_identifiers, init_db, upsert_lookup

        init_db()
        work = _make_work(doi="10.1000/abc", arxiv_id="2101.12345", openalex_id="W99999")
        upsert_lookup(work)

        result = get_identifiers(work.work_key)
        assert result is not None
        assert result["doi_norm"] == "10.1000/abc"
        assert result["arxiv_id_norm"] == "2101.12345"
        assert result["openalex_id"] == "W99999"

    def test_get_returns_none_for_unknown_key(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import get_identifiers, init_db

        init_db()
        assert get_identifiers("wrk_doesnotexist") is None

    def test_upsert_updates_existing_row(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import get_identifiers, init_db, upsert_lookup

        init_db()
        work = _make_work(doi="10.1000/abc", openalex_id="W111")
        upsert_lookup(work)

        # Update with a new openalex_id on the same work_key
        work2 = work.model_copy(deep=True)
        work2.identifiers.openalex_id = "W222"
        upsert_lookup(work2)

        result = get_identifiers(work.work_key)
        assert result is not None
        assert result["openalex_id"] == "W222"

    def test_upsert_works_with_null_identifiers(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import get_identifiers, init_db, upsert_lookup

        init_db()
        work = _make_work(title="No IDs Paper", doi=None, arxiv_id=None, openalex_id=None)
        upsert_lookup(work)

        result = get_identifiers(work.work_key)
        assert result is not None
        assert result["doi_norm"] is None
        assert result["arxiv_id_norm"] is None
        assert result["openalex_id"] is None

    def test_touch_last_seen_does_not_raise(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import init_db, touch_last_seen, upsert_lookup

        init_db()
        work = _make_work(doi="10.1000/touch")
        upsert_lookup(work)
        touch_last_seen(work.work_key)  # should not raise

    def test_get_identifiers_returns_none_when_db_missing(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "nonexistent" / "db.sqlite")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import get_identifiers

        # DB not initialized — should return None gracefully
        result = get_identifiers("wrk_anything")
        assert result is None


# ---------------------------------------------------------------------------
# Server DB fallback integration tests
# ---------------------------------------------------------------------------

class TestServerDbFallback:
    async def test_get_work_uses_db_after_cache_cleared(self, tmp_path, monkeypatch):
        """get_work should resolve a work from DB when _WORK_CACHE is empty."""
        db_path = str(tmp_path / "srv_test.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import init_db, upsert_lookup
        from scholarly_gateway import server

        init_db()

        # Build a work with an OpenAlex ID and store it in the test DB
        work = _make_work(doi="10.1000/srv", openalex_id="W55555")
        upsert_lookup(work)

        # Clear the in-process cache so the tool will miss
        server._WORK_CACHE.clear()

        # Mock openalex_provider.fetch_work to return the same work
        monkeypatch.setattr(
            server.openalex_provider,
            "fetch_work",
            AsyncMock(return_value=(work, ProviderStatus(status="ok"))),
        )

        result = await server.get_work(work.work_key)

        assert result["work"]["work_key"] == work.work_key
        assert "not found" not in result["markdown"].lower()
        # Work is now back in cache
        assert work.work_key in server._WORK_CACHE

    async def test_get_work_falls_back_to_arxiv_when_no_openalex(self, tmp_path, monkeypatch):
        """When only arxiv_id_norm is in the DB, fetch via arXiv provider."""
        db_path = str(tmp_path / "srv_arxiv.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import init_db, upsert_lookup
        from scholarly_gateway import server

        init_db()

        work = _make_work(arxiv_id="2101.12345")
        upsert_lookup(work)
        server._WORK_CACHE.clear()

        monkeypatch.setattr(
            server.arxiv_provider,
            "fetch_work",
            AsyncMock(return_value=(work, ProviderStatus(status="ok"))),
        )

        result = await server.get_work(work.work_key)

        assert result["work"]["work_key"] == work.work_key
        assert "not found" not in result["markdown"].lower()

    async def test_get_work_returns_not_found_when_db_empty(self, tmp_path, monkeypatch):
        """When neither cache nor DB has the key, return not-found response."""
        db_path = str(tmp_path / "empty.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_DB_PATH", db_path)

        from scholarly_gateway.storage import init_db
        from scholarly_gateway import server

        init_db()
        server._WORK_CACHE.clear()

        result = await server.get_work("wrk_0000000000000000")

        assert "not found" in result["markdown"].lower()
