"""Append-only intel provenance ledger — internal use only.

One table: ledger_event
One write type: append_event (INSERT OR IGNORE)
No reads. No other write types.

Only activated when SCHOLARLY_GATEWAY_INTEL_ENABLED is truthy.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ledger_event (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    source_provider TEXT,
    work_key        TEXT,
    payload_json    TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL
)
"""

_INSERT_EVENT = """
INSERT OR IGNORE INTO ledger_event
    (event_id, event_type, observed_at, source_provider, work_key,
     payload_json, payload_sha256)
VALUES
    (?, ?, ?, ?, ?, ?, ?)
"""


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8 safe."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class IntelLedger:
    """SQLite-backed append-only ledger for tool-call provenance events."""

    def __init__(self, db_path: str) -> None:
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def append_event(
        self,
        event_type: str,
        payload: Any,
        *,
        observed_at: Optional[str] = None,
        source_provider: Optional[str] = None,
        work_key: Optional[str] = None,
    ) -> None:
        if observed_at is None:
            observed_at = datetime.now(timezone.utc).isoformat()

        payload_json = canonical_json(payload)
        payload_sha256 = _sha256_hex(payload_json)

        event_dict_without_id: dict[str, Any] = {
            "event_type": event_type,
            "observed_at": observed_at,
            "payload_json": payload_json,
            "payload_sha256": payload_sha256,
            "source_provider": source_provider,
            "work_key": work_key,
        }
        event_id = _sha256_hex(canonical_json(event_dict_without_id))

        self._conn.execute(
            _INSERT_EVENT,
            (
                event_id,
                event_type,
                observed_at,
                source_provider,
                work_key,
                payload_json,
                payload_sha256,
            ),
        )
        self._conn.commit()
