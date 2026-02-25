"""TOOL_CALL ledger coverage tests for search_works and get_work.

C1 - Calling search_works writes a ledger row.
C2 - Calling get_work writes a ledger row.
C3 - Together they produce exactly 2 distinct rows.
C4 - Repeating the identical call is idempotent (same event_id; row count unchanged).

Reads (SELECT) are test-only; no production read paths are exposed (I5).
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime

import scholarly_gateway.server as server_mod


FIXED_TS = "2024-01-01T00:00:00+00:00"


def _row_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM ledger_event").fetchone()
        return count
    finally:
        conn.close()


def _fetch_rows(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM ledger_event").fetchall()]
    finally:
        conn.close()


def _enable_intel(monkeypatch, db_path: str) -> None:
    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "1")
    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_DB_PATH", db_path)
    monkeypatch.setattr(server_mod, "_intel_sink", None)
    monkeypatch.setattr(server_mod, "_intel_initialized", False)


class TestSearchWorksEmission:
    """C1: search_works writes a TOOL_CALL row when intel is enabled."""

    def test_search_works_emits_one_row(self, monkeypatch, tmp_path):
        """C1: search_works with no providers writes one ledger row."""
        db_path = str(tmp_path / "ledger.db")
        _enable_intel(monkeypatch, db_path)
        server_mod._WORK_CACHE.clear()

        asyncio.run(
            server_mod.search_works(query="attention is all you need", providers=[])
        )

        assert _row_count(db_path) == 1


class TestGetWorkEmission:
    """C2: get_work writes a TOOL_CALL row when intel is enabled."""

    def test_get_work_unknown_key_emits_one_row(self, monkeypatch, tmp_path):
        """C2: get_work with an unknown key (not-found path) emits a row."""
        db_path = str(tmp_path / "ledger.db")
        _enable_intel(monkeypatch, db_path)
        server_mod._WORK_CACHE.clear()

        asyncio.run(server_mod.get_work(work_key="wrk_doesnotexist"))

        assert _row_count(db_path) == 1


class TestBothToolsDistinctRows:
    """C3: search_works and get_work each emit one row, totalling 2 distinct rows."""

    def test_two_tools_produce_two_rows(self, monkeypatch, tmp_path):
        """C3: distinct payloads from two tools produce two distinct ledger rows."""
        db_path = str(tmp_path / "ledger.db")
        _enable_intel(monkeypatch, db_path)
        server_mod._WORK_CACHE.clear()

        asyncio.run(server_mod.search_works(query="coverage query", providers=[]))
        asyncio.run(server_mod.get_work(work_key="wrk_coverage"))

        rows = _fetch_rows(db_path)
        assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
        assert rows[0]["event_id"] != rows[1]["event_id"]


class TestIdempotency:
    """C4: repeating the identical tool call is idempotent."""

    def test_repeated_get_work_call_is_idempotent(self, monkeypatch, tmp_path):
        """C4: get_work twice with same args and frozen clock yields one row."""
        import scholarly_gateway.intel_ledger as ledger_mod

        db_path = str(tmp_path / "ledger.db")
        _enable_intel(monkeypatch, db_path)
        server_mod._WORK_CACHE.clear()

        fixed_dt = datetime.fromisoformat(FIXED_TS)

        class _FakeDatetime:
            @staticmethod
            def now(tz=None):
                return fixed_dt

        monkeypatch.setattr(ledger_mod, "datetime", _FakeDatetime)

        asyncio.run(server_mod.get_work(work_key="wrk_idempotent"))
        asyncio.run(server_mod.get_work(work_key="wrk_idempotent"))

        rows = _fetch_rows(db_path)
        assert len(rows) == 1, "Repeated identical call must not create a second row"

        first_event_id = rows[0]["event_id"]

        asyncio.run(server_mod.get_work(work_key="wrk_idempotent"))
        rows_after = _fetch_rows(db_path)
        assert len(rows_after) == 1
        assert rows_after[0]["event_id"] == first_event_id
