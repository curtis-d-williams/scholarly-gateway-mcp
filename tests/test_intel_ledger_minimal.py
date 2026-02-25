"""Minimal intel ledger tests (T5 extension).

Test 1: intel disabled -> search_works does NOT create any DB file.
Test 2: intel enabled + unwritable DB path -> search_works still succeeds
        and output matches committed golden.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import stat

import pytest

from scholarly_gateway.models import ProviderStatus
from scholarly_gateway.providers.arxiv import _parse_feed as ax_parse_feed

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"
FIXED_TIMESTAMP = "2024-01-01T00:00:00+00:00"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _build_vit_work(monkeypatch):
    import scholarly_gateway.providers.arxiv as arxiv_mod
    monkeypatch.setattr(arxiv_mod, "_now_iso", lambda: FIXED_TIMESTAMP)
    xml = (FIXTURES / "arxiv_2010.11929.xml").read_text(encoding="utf-8")
    works = ax_parse_feed(xml)
    assert len(works) == 1
    return works[0]


def _stub_arxiv_search(vit_work):
    async def _stub(query, filters, sort="relevance", limit=10, start=0):
        return ([vit_work], None, ProviderStatus(status="ok", http_status=200))
    return _stub


def _reset_intel(monkeypatch):
    """Reset server-level memoized intel sink so env changes take effect."""
    import scholarly_gateway.server as server_mod
    monkeypatch.setattr(server_mod, "_intel_sink", None)
    monkeypatch.setattr(server_mod, "_intel_initialized", False)


# ---------------------------------------------------------------------------
# Test 1: disabled — no DB file created at the explicit tmp path
# ---------------------------------------------------------------------------

def test_intel_disabled_no_db_created(monkeypatch, tmp_path):
    """When intel is disabled, search_works must not create any DB file."""
    db_path = tmp_path / "should_not_exist.db"

    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "0")
    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_DB_PATH", str(db_path))
    _reset_intel(monkeypatch)

    vit_work = _build_vit_work(monkeypatch)
    import scholarly_gateway.providers.arxiv as arxiv_mod
    monkeypatch.setattr(arxiv_mod, "search", _stub_arxiv_search(vit_work))

    import scholarly_gateway.server as server_mod
    server_mod._WORK_CACHE.clear()
    asyncio.run(server_mod.search_works(query="id:2010.11929", providers=["arxiv"]))

    assert not db_path.exists(), "DB file must not be created when intel is disabled"


# ---------------------------------------------------------------------------
# Test 2: enabled + unwritable path -> fail-open, golden still matches
# ---------------------------------------------------------------------------

def test_intel_enabled_unwritable_path_fail_open(monkeypatch, tmp_path):
    """With intel enabled and an unwritable DB path, search_works still succeeds."""
    # Create a read+execute-only directory; writing inside it will fail.
    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    locked_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

    db_path = locked_dir / "intel.db"

    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "1")
    monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_DB_PATH", str(db_path))
    _reset_intel(monkeypatch)

    vit_work = _build_vit_work(monkeypatch)
    import scholarly_gateway.providers.arxiv as arxiv_mod
    monkeypatch.setattr(arxiv_mod, "search", _stub_arxiv_search(vit_work))

    import scholarly_gateway.server as server_mod
    server_mod._WORK_CACHE.clear()
    result = asyncio.run(server_mod.search_works(query="id:2010.11929", providers=["arxiv"]))

    # Restore permissions so tmp_path cleanup succeeds
    locked_dir.chmod(stat.S_IRWXU)

    # Must match the committed golden — output unchanged by intel failure
    golden_path = GOLDEN_DIR / "search_works" / "arxiv_id_lookup.json"
    assert golden_path.exists(), "Golden file must exist"
    expected = golden_path.read_text(encoding="utf-8")
    assert canonical(result) == expected, (
        f"Output does not match golden after intel fail-open.\n"
        f"  expected (first 300): {expected[:300]!r}\n"
        f"  actual   (first 300): {canonical(result)[:300]!r}"
    )
