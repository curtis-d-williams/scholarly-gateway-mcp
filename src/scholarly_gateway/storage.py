"""SQLite-backed lookup store for work_key → identifiers."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scholarly_gateway.models import InternalWork

_DEFAULT_DB_PATH = "./.data/scholarly_gateway.db"


def _get_db_path() -> str:
    return os.environ.get("SCHOLARLY_GATEWAY_DB_PATH", _DEFAULT_DB_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Initialize the SQLite database and create the work_lookup table."""
    db_path = _get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_lookup (
                work_key TEXT PRIMARY KEY,
                doi_norm TEXT,
                arxiv_id_norm TEXT,
                openalex_id TEXT,
                created_at TEXT,
                last_seen_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def upsert_lookup(work: InternalWork) -> None:
    """Insert or update identifier data for a work in the DB."""
    db_path = _get_db_path()
    now = _now_iso()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO work_lookup
                (work_key, doi_norm, arxiv_id_norm, openalex_id, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_key) DO UPDATE SET
                doi_norm = excluded.doi_norm,
                arxiv_id_norm = excluded.arxiv_id_norm,
                openalex_id = excluded.openalex_id,
                last_seen_at = excluded.last_seen_at
            """,
            (
                work.work_key,
                work.identifiers.doi,
                work.identifiers.arxiv_id,
                work.identifiers.openalex_id,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_identifiers(work_key: str) -> Optional[dict]:
    """Return identifier dict for a work_key, or None if not found."""
    db_path = _get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT doi_norm, arxiv_id_norm, openalex_id FROM work_lookup WHERE work_key = ?",
                (work_key,),
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if row is None:
        return None
    return {
        "doi_norm": row[0],
        "arxiv_id_norm": row[1],
        "openalex_id": row[2],
    }


def touch_last_seen(work_key: str) -> None:
    """Update last_seen_at timestamp for a work."""
    db_path = _get_db_path()
    now = _now_iso()
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "UPDATE work_lookup SET last_seen_at = ? WHERE work_key = ?",
                (now, work_key),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
