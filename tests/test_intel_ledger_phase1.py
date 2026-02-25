"""Phase 1 ledger hardening tests.

B1 — Idempotency: recording the exact same canonical event twice yields the
     same event_id and only one DB row.
B2 — Stress idempotency: recording N times still yields one row.
B3 — Integrity: event_id equals sha256(canonical_event_json) for stored rows.
B4 — Fail-open: a write failure after successful init does not propagate from
     IntelSink.record_event.

Reads (SELECT) are used here only to count rows and validate stored values.
No read paths are exposed in production code (I5).
"""
from __future__ import annotations

import sqlite3

import pytest

from scholarly_gateway.intel_ledger import IntelLedger, _sha256_hex, canonical_json

FIXED_TS = "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers — test-only DB reads
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# B1/B2 — Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """B1 and B2: same canonical event recorded N times → exactly one row."""

    def test_same_event_twice_yields_one_row(self, tmp_path):
        """B1: two identical append_event calls → one DB row (INSERT OR IGNORE)."""
        db_path = str(tmp_path / "ledger.db")
        ledger = IntelLedger(db_path)

        kwargs = dict(
            event_type="TOOL_CALL",
            payload={"query": "attention is all you need", "tool": "search_works"},
            observed_at=FIXED_TS,
            source_provider="arxiv",
            work_key=None,
        )

        ledger.append_event(**kwargs)
        ledger.append_event(**kwargs)

        assert _row_count(db_path) == 1, "Duplicate event must not create a second row"

    def test_same_event_twice_produces_same_event_id(self, tmp_path):
        """B1: the single stored row's event_id is deterministic across calls."""
        db_path = str(tmp_path / "ledger.db")
        ledger = IntelLedger(db_path)

        kwargs = dict(
            event_type="TOOL_CALL",
            payload={"query": "determinism", "tool": "search_works"},
            observed_at=FIXED_TS,
            source_provider=None,
            work_key=None,
        )

        ledger.append_event(**kwargs)
        ledger.append_event(**kwargs)

        rows = _fetch_rows(db_path)
        assert len(rows) == 1

        # Recompute expected event_id independently of IntelLedger internals
        payload_json = canonical_json({"query": "determinism", "tool": "search_works"})
        payload_sha256 = _sha256_hex(payload_json)
        event_dict = {
            "event_type": "TOOL_CALL",
            "observed_at": FIXED_TS,
            "payload_json": payload_json,
            "payload_sha256": payload_sha256,
            "source_provider": None,
            "work_key": None,
        }
        expected_id = _sha256_hex(canonical_json(event_dict))

        assert rows[0]["event_id"] == expected_id

    def test_stress_idempotency_fifty_calls(self, tmp_path):
        """B2: 50 identical recordings → exactly one DB row."""
        db_path = str(tmp_path / "ledger.db")
        ledger = IntelLedger(db_path)

        for _ in range(50):
            ledger.append_event(
                event_type="TOOL_CALL",
                payload={"tool": "search_works", "query": "stress test"},
                observed_at=FIXED_TS,
            )

        assert _row_count(db_path) == 1, "50 identical events must collapse to one row"


# ---------------------------------------------------------------------------
# B3 — Integrity
# ---------------------------------------------------------------------------

class TestIntegrity:
    """B3: event_id stored in DB must equal sha256(canonical_event_json)."""

    def test_event_id_equals_sha256_of_canonical_event(self, tmp_path):
        """Stored event_id is always reproducible from the row's own sibling columns."""
        db_path = str(tmp_path / "ledger.db")
        ledger = IntelLedger(db_path)

        ledger.append_event(
            event_type="TOOL_CALL",
            payload={"tool": "get_work", "work_key": "wrk_abc123"},
            observed_at=FIXED_TS,
            source_provider="openalex",
            work_key="wrk_abc123",
        )

        rows = _fetch_rows(db_path)
        assert len(rows) == 1
        row = rows[0]

        # Reconstruct event_id from stored columns (must match what IntelLedger wrote)
        recomputed_id = _sha256_hex(
            canonical_json({
                "event_type": row["event_type"],
                "observed_at": row["observed_at"],
                "payload_json": row["payload_json"],
                "payload_sha256": row["payload_sha256"],
                "source_provider": row["source_provider"],
                "work_key": row["work_key"],
            })
        )

        assert row["event_id"] == recomputed_id, (
            f"Stored event_id {row['event_id']!r} does not match "
            f"recomputed {recomputed_id!r}"
        )

    def test_payload_sha256_matches_payload_json(self, tmp_path):
        """payload_sha256 stored in DB must equal sha256(payload_json)."""
        db_path = str(tmp_path / "ledger.db")
        ledger = IntelLedger(db_path)

        ledger.append_event(
            event_type="TOOL_CALL",
            payload={"providers": ["arxiv", "openalex"], "query": "ViT"},
            observed_at=FIXED_TS,
        )

        rows = _fetch_rows(db_path)
        row = rows[0]

        assert row["payload_sha256"] == _sha256_hex(row["payload_json"]), (
            "payload_sha256 must be sha256 of payload_json"
        )


# ---------------------------------------------------------------------------
# B4 — Fail-open
# ---------------------------------------------------------------------------

class TestFailOpen:
    """B4: write failure after successful init must not propagate from IntelSink."""

    def test_record_event_write_failure_is_swallowed(self, tmp_path, monkeypatch):
        """IntelSink.record_event catches exceptions — callers never see DB errors."""
        from scholarly_gateway.intel import IntelSink

        db_path = str(tmp_path / "ledger.db")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "1")
        monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_DB_PATH", db_path)

        sink = IntelSink()

        # Simulate a write failure by patching IntelLedger.append_event directly.
        # (sqlite3.Connection.execute is a read-only C attribute and cannot be
        # monkeypatched; patching the Python-level method is the correct approach.)
        def _raise(*args, **kwargs):
            raise sqlite3.OperationalError("simulated disk full")

        monkeypatch.setattr(sink._ledger, "append_event", _raise)

        # Must not raise — fail-open contract
        sink.record_event("TOOL_CALL", {"tool": "search_works", "query": "fail test"})

    def test_get_intel_sink_returns_none_on_init_failure(self, monkeypatch):
        """get_intel_sink() returns None when IntelSink constructor raises."""
        import scholarly_gateway.intel as intel_mod

        monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "1")

        class _BrokenSink:
            def __init__(self) -> None:
                raise RuntimeError("simulated broken init")

        monkeypatch.setattr(intel_mod, "IntelSink", _BrokenSink)

        assert intel_mod.get_intel_sink() is None, (
            "get_intel_sink must return None when IntelSink init fails"
        )
