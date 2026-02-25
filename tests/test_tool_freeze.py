"""T1 — Tool Surface Freeze Test
T2 — Schema Snapshot Freeze Test

These tests assert that the exact set of V1 tool names and their input/output
schemas are frozen.  Any change to a tool name or schema will cause CI to fail
and must be explicitly approved by Curtis.

Snapshot files live in tests/schema_snapshots/ and must be committed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib

import pytest

from scholarly_gateway.server import mcp

SNAPSHOT_DIR = pathlib.Path(__file__).parent / "schema_snapshots"

FROZEN_TOOLS = frozenset({
    "search_works",
    "get_work",
    "get_abstract",
    "get_fulltext_links",
    "forward_citations",
    "backward_references",
    "export_citation",
    "compare_versions",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def canonical(obj) -> str:
    """Canonical JSON: sorted keys, compact separators, UTF-8 safe."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def get_tools_sync():
    """Enumerate live tools from the MCP server synchronously."""
    return asyncio.run(mcp.list_tools())


# ---------------------------------------------------------------------------
# T1 — Tool Surface Freeze
# ---------------------------------------------------------------------------

class TestT1ToolSurfaceFreeze:
    def test_exact_tool_count(self):
        tools = get_tools_sync()
        assert len(tools) == 8, (
            f"Expected exactly 8 tools, got {len(tools)}: "
            f"{sorted(t.name for t in tools)}"
        )

    def test_exact_tool_names(self):
        tools = get_tools_sync()
        actual = frozenset(t.name for t in tools)
        assert actual == FROZEN_TOOLS, (
            f"Tool surface mismatch.\n"
            f"  Missing: {FROZEN_TOOLS - actual}\n"
            f"  Extra:   {actual - FROZEN_TOOLS}"
        )


# ---------------------------------------------------------------------------
# T2 — Schema Snapshot Freeze
# ---------------------------------------------------------------------------

class TestT2SchemaSnapshotFreeze:
    @pytest.fixture(scope="class")
    def live_tools(self):
        tools = get_tools_sync()
        return {t.name: t for t in tools}

    @pytest.fixture(scope="class")
    def manifest(self):
        path = SNAPSHOT_DIR / "tools.json"
        assert path.exists(), f"Snapshot manifest missing: {path}"
        return json.loads(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("tool_name", sorted(FROZEN_TOOLS))
    def test_input_schema_matches_snapshot(self, live_tools, tool_name):
        tool = live_tools[tool_name]
        live_canon = canonical(tool.parameters)
        snapshot_path = SNAPSHOT_DIR / f"{tool_name}.input.schema.json"
        assert snapshot_path.exists(), f"Snapshot missing: {snapshot_path}"
        snapshot_canon = snapshot_path.read_text(encoding="utf-8")
        assert live_canon == snapshot_canon, (
            f"Input schema changed for tool '{tool_name}'.\n"
            f"  Snapshot: {snapshot_canon}\n"
            f"  Live:     {live_canon}"
        )

    @pytest.mark.parametrize("tool_name", sorted(FROZEN_TOOLS))
    def test_output_schema_matches_snapshot(self, live_tools, tool_name):
        tool = live_tools[tool_name]
        live_canon = canonical(tool.output_schema)
        snapshot_path = SNAPSHOT_DIR / f"{tool_name}.output.schema.json"
        assert snapshot_path.exists(), f"Snapshot missing: {snapshot_path}"
        snapshot_canon = snapshot_path.read_text(encoding="utf-8")
        assert live_canon == snapshot_canon, (
            f"Output schema changed for tool '{tool_name}'.\n"
            f"  Snapshot: {snapshot_canon}\n"
            f"  Live:     {live_canon}"
        )

    @pytest.mark.parametrize("tool_name", sorted(FROZEN_TOOLS))
    def test_manifest_digests_match_snapshots(self, manifest, tool_name):
        entry = next(
            (e for e in manifest["tools"] if e["name"] == tool_name), None
        )
        assert entry is not None, f"Tool '{tool_name}' missing from tools.json"

        in_canon = (SNAPSHOT_DIR / f"{tool_name}.input.schema.json").read_text(encoding="utf-8")
        out_canon = (SNAPSHOT_DIR / f"{tool_name}.output.schema.json").read_text(encoding="utf-8")

        assert sha256_of(in_canon) == entry["input_schema_sha256"], (
            f"tools.json input digest mismatch for '{tool_name}'"
        )
        assert sha256_of(out_canon) == entry["output_schema_sha256"], (
            f"tools.json output digest mismatch for '{tool_name}'"
        )
