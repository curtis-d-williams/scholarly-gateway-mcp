"""T5 — Intel feature-flag fail-open test.

Verifies that when SCHOLARLY_GATEWAY_INTEL_ENABLED=1 but intel initialisation
fails, the system gracefully falls back to disabled behaviour (fail-open) with
absolutely no effect on tool outputs.

Python import-binding note: server.py binds `get_intel_sink` at import time via
  `from scholarly_gateway.intel import get_intel_sink`
The function object itself looks up `IntelSink` from scholarly_gateway.intel's
module dict at call time. Patching scholarly_gateway.intel.IntelSink therefore
causes get_intel_sink()'s existing try/except to trigger, returning None — the
correct production fail-open code path. server._intel() then also returns None.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from scholarly_gateway.models import ProviderStatus
from scholarly_gateway.providers.arxiv import _parse_feed as ax_parse_feed

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"
FIXED_TIMESTAMP = "2024-01-01T00:00:00+00:00"


def canonical(obj) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8 safe."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class TestT5IntelFailOpen:
    """T5: intel flag fail-open — init failure yields None, tool outputs unchanged."""

    def test_intel_fail_open_and_tool_output_unchanged(self, monkeypatch):
        """When IntelSink init raises, get_intel_sink returns None (fail-open).

        We simulate an intel initialisation failure by replacing IntelSink with
        a broken class whose __init__ raises.  get_intel_sink()'s existing
        try/except catches it and returns None.  server._intel() then returns
        None too.  Finally we assert the golden tool output is byte-equal.
        """
        import scholarly_gateway.intel as intel_mod
        from scholarly_gateway import server

        # 1. Enable the feature flag.
        monkeypatch.setenv("SCHOLARLY_GATEWAY_INTEL_ENABLED", "1")

        # 2. Make IntelSink construction raise — simulates init failure.
        #    get_intel_sink() looks up IntelSink from intel_mod's module dict at
        #    call time, so this patch is effective even via server.py's binding.
        class _BrokenSink:
            def __init__(self) -> None:
                raise RuntimeError("simulated intel init failure")

        monkeypatch.setattr(intel_mod, "IntelSink", _BrokenSink)

        # 3. get_intel_sink() must catch the error and return None (fail-open).
        assert intel_mod.get_intel_sink() is None

        # 4. Reset server memoisation so _intel() re-evaluates with the patch active.
        monkeypatch.setattr(server, "_intel_initialized", False)
        monkeypatch.setattr(server, "_intel_sink", None)

        # 5. server._intel() must also return None.
        assert server._intel() is None

        # 6. Tool output must be byte-equal to the committed golden.
        import scholarly_gateway.providers.arxiv as arxiv_mod

        monkeypatch.setattr(arxiv_mod, "_now_iso", lambda: FIXED_TIMESTAMP)
        xml = (FIXTURES / "arxiv_2010.11929.xml").read_text(encoding="utf-8")
        vit_work = ax_parse_feed(xml)[0]

        server._WORK_CACHE.clear()

        async def _stub_arxiv_search(query, filters, sort="relevance", limit=10, start=0):
            return ([vit_work], None, ProviderStatus(status="ok", http_status=200))

        monkeypatch.setattr(arxiv_mod, "search", _stub_arxiv_search)

        result = asyncio.run(
            server.search_works(query="id:2010.11929", providers=["arxiv"])
        )

        golden_path = GOLDEN_DIR / "search_works" / "arxiv_id_lookup.json"
        assert golden_path.exists(), f"Missing golden: {golden_path}"
        assert canonical(result) == golden_path.read_text(encoding="utf-8"), (
            "Tool output changed when intel fail-open path is active"
        )
