"""Freeze the MCP tool surface (names + input-parameter schemas).

Any addition, removal, rename, or parameter-schema change will fail CI.
All expected values are baked in as constants — no snapshot files, no network.
"""
from __future__ import annotations

import asyncio
import hashlib

from scholarly_gateway.server import mcp
from scholarly_gateway.intel_ledger import canonical_json

# ---------------------------------------------------------------------------
# Frozen constants — generated from the V1 implementation at authoring time.
# To update: re-run the introspection snippet, paste new values, commit.
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset({
    "backward_references",
    "compare_versions",
    "export_citation",
    "forward_citations",
    "get_abstract",
    "get_fulltext_links",
    "get_work",
    "search_works",
})

# sha256( canonical_json(tool.parameters) ) for each tool, keyed by tool name.
EXPECTED_INPUT_SCHEMA_DIGESTS: dict[str, str] = {
    "backward_references": "8a75cf2a12eee1e2c1d7e510b8cd9f049956b53c863de725fcd403b913f629a5",
    "compare_versions":    "0d989d5108ed89e9118e1140757685bbddf69b9e35688a69e616da313fd30247",
    "export_citation":     "42f60b2789aba917b8c97dc8665667da39b75dc2bfbe0e44b1d44222f143647c",
    "forward_citations":   "8a75cf2a12eee1e2c1d7e510b8cd9f049956b53c863de725fcd403b913f629a5",
    "get_abstract":        "56419d2a8f0572cfb14bc3bb9bed34dfd21cbb3b1a9d6fa79338631211ec2795",
    "get_fulltext_links":  "0d989d5108ed89e9118e1140757685bbddf69b9e35688a69e616da313fd30247",
    "get_work":            "0d989d5108ed89e9118e1140757685bbddf69b9e35688a69e616da313fd30247",
    "search_works":        "98cd22773a6b298885e3ccfefac3ded8bacdd9f5be7d4bbf4d243dfdbfbf9fe2",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _live_tools() -> dict[str, object]:
    """Return {name: tool} sorted by name, via synchronous introspection."""
    tools = asyncio.run(mcp.list_tools())
    return {t.name: t for t in sorted(tools, key=lambda t: t.name)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolSurfaceFreeze:
    """Assert the exact V1 MCP tool surface cannot drift silently."""

    def test_exact_tool_names(self) -> None:
        """Tool set must be an exact match — no extras, no missing."""
        live = frozenset(_live_tools().keys())
        assert live == EXPECTED_TOOL_NAMES, (
            f"Tool surface changed.\n"
            f"  Missing : {EXPECTED_TOOL_NAMES - live}\n"
            f"  Extra   : {live - EXPECTED_TOOL_NAMES}"
        )

    def test_input_schema_digests(self) -> None:
        """Every tool's input-parameter schema must hash to the frozen digest."""
        live_tools = _live_tools()
        failures: list[str] = []

        for name in sorted(EXPECTED_TOOL_NAMES):
            tool = live_tools.get(name)
            if tool is None:
                failures.append(f"{name}: tool missing from live registry")
                continue

            canon = canonical_json(tool.parameters)
            live_digest = _sha256(canon)
            expected_digest = EXPECTED_INPUT_SCHEMA_DIGESTS[name]

            if live_digest != expected_digest:
                failures.append(
                    f"{name}: schema changed\n"
                    f"    expected digest : {expected_digest}\n"
                    f"    live digest     : {live_digest}\n"
                    f"    live canonical  : {canon}"
                )

        assert not failures, "Input schema drift detected:\n" + "\n".join(failures)
