"""Scholarly Gateway MCP server — V1 implementation."""
from __future__ import annotations

import base64
import json
from typing import Any, Literal, Optional

from fastmcp import FastMCP

from scholarly_gateway import providers
from scholarly_gateway.formatting import (
    render_citations_list,
    render_search_results,
    render_work_detail,
)
from scholarly_gateway.identity import (
    generate_cluster_key,
    generate_work_key,
    merge_work_lists,
    normalize_arxiv_id,
    normalize_doi,
)
from scholarly_gateway.models import (
    CitationsOutput,
    CompareVersionsOutput,
    ExportCitationOutput,
    GetAbstractOutput,
    GetFulltextLinksOutput,
    GetWorkOutput,
    InternalWork,
    ProviderStatus,
    SearchWorksOutput,
    VersionEntry,
)
from scholarly_gateway.providers import arxiv as arxiv_provider
from scholarly_gateway.providers import openalex as openalex_provider

mcp = FastMCP("scholarly-gateway")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_cursor(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_cursor(token: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception:
        return {}


def _resolve_work_key(work_key: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract embedded identifiers from work_key if stored in registry.

    For V1, the work_key is opaque. Resolution must come from a cache or
    re-parsing. We return (doi, arxiv_id, openalex_id) as None if unknown.
    """
    # V1: We cannot reverse the hash. The caller should pass structured
    # input when they have identifiers. For tools that take work_key, we
    # rely on a short-lived in-process cache populated at search time.
    return _WORK_CACHE.get(work_key, (None, None, None))


# In-process work cache: work_key -> InternalWork
_WORK_CACHE: dict[str, InternalWork] = {}


def _cache_works(works: list[InternalWork]) -> None:
    for w in works:
        _WORK_CACHE[w.work_key] = w


def _ok_status() -> ProviderStatus:
    return ProviderStatus(status="ok")


def _not_supported_status() -> ProviderStatus:
    return ProviderStatus(status="not_supported", message="Not supported by this provider in V1")


# ---------------------------------------------------------------------------
# Tool: search_works
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_works(
    query: str,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    kind: Optional[str] = None,
    oa_only: bool = False,
    providers: Optional[list[str]] = None,
    sort: Literal["relevance", "recency", "citations"] = "relevance",
    limit: int = 10,
    cursor: Optional[str] = None,
) -> dict:
    """Search academic works across OpenAlex and arXiv.

    Returns a list of works (InternalWork spine objects) and a markdown table.
    """
    limit = min(limit, 25)
    filters = {
        "year_from": year_from,
        "year_to": year_to,
        "kind": kind,
        "oa_only": oa_only,
    }

    active_providers = providers or ["openalex", "arxiv"]

    # Decode cursor
    cursor_data: dict = _decode_cursor(cursor) if cursor else {}

    # --- OpenAlex ---
    oa_works: list[InternalWork] = []
    oa_status = ProviderStatus(status="not_supported")
    oa_next_cursor: Optional[str] = None

    if "openalex" in active_providers:
        oa_cursor = cursor_data.get("openalex")
        try:
            oa_works, oa_next_cursor, oa_status = await openalex_provider.search(
                query=query,
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=oa_cursor,
            )
        except Exception as e:
            oa_status = ProviderStatus(status="error", message=str(e))

    # --- arXiv ---
    ax_works: list[InternalWork] = []
    ax_status = ProviderStatus(status="not_supported")
    ax_next_start: Optional[int] = None

    if "arxiv" in active_providers:
        ax_start = cursor_data.get("arxiv_start", 0)
        try:
            ax_works, ax_next_start, ax_status = await arxiv_provider.search(
                query=query,
                filters=filters,
                sort=sort,
                limit=limit,
                start=ax_start,
            )
        except Exception as e:
            ax_status = ProviderStatus(status="error", message=str(e))

    # Merge
    merged = merge_work_lists([oa_works, ax_works])
    merged = merged[:limit]

    _cache_works(merged)

    # Build next cursor
    next_cursor: Optional[str] = None
    if oa_next_cursor or ax_next_start is not None:
        next_cursor_data: dict[str, Any] = {}
        if oa_next_cursor:
            next_cursor_data["openalex"] = oa_next_cursor
        if ax_next_start is not None:
            next_cursor_data["arxiv_start"] = ax_next_start
        next_cursor = _encode_cursor(next_cursor_data)

    provider_status = {
        "openalex": oa_status,
        "arxiv": ax_status,
    }

    markdown = render_search_results(merged)

    output = SearchWorksOutput(
        results=merged,
        markdown=markdown,
        next_cursor=next_cursor,
        provider_status=provider_status,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Tool: get_work
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_work(work_key: str) -> dict:
    """Retrieve full details for a work by its work_key.

    Uses cached data from previous search, or fetches from providers by
    work_key-embedded identifiers.
    """
    cached = _WORK_CACHE.get(work_key)
    provider_status: dict[str, ProviderStatus] = {
        "openalex": _ok_status(),
        "arxiv": _ok_status(),
    }

    if cached:
        md = render_work_detail(cached)
        return GetWorkOutput(
            work=cached,
            markdown=md,
            provider_status=provider_status,
        ).model_dump()

    # Not in cache — cannot reverse hash; return error
    return GetWorkOutput(
        work=InternalWork(
            work_key=work_key,
            cluster_key=work_key.replace("wrk_", "clu_"),
            key_strength="weak",
            bibliographic={"title": "Work not found"},  # type: ignore[arg-type]
            provenance={},  # type: ignore[arg-type]
        ),
        markdown=f"_Work `{work_key}` not found in cache. Run `search_works` first._",
        provider_status={
            "openalex": ProviderStatus(status="error", message="Not in cache"),
            "arxiv": ProviderStatus(status="error", message="Not in cache"),
        },
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: get_abstract
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_abstract(
    work_key: str,
    mode: Literal["teaser", "full"] = "teaser",
) -> dict:
    """Get abstract text for a work.

    mode="teaser": returns first ~300 chars.
    mode="full": returns full abstract if available.
    """
    cached = _WORK_CACHE.get(work_key)
    if not cached:
        return GetAbstractOutput(
            work_key=work_key,
            mode=mode,
            abstract_text=None,
            source_provider=None,
        ).model_dump()

    abstract_text = cached.abstract.teaser
    source_provider = cached.provenance.records[0].provider if cached.provenance.records else None

    if mode == "full" and cached.identifiers.arxiv_id:
        # Fetch full abstract from arXiv
        try:
            work, ax_status = await arxiv_provider.fetch_work(cached.identifiers.arxiv_id)
            if work and work.abstract.teaser:
                # arXiv returns full summary in Atom feed
                abstract_text = work.abstract.teaser
                source_provider = "arxiv"
        except Exception:
            pass
    elif mode == "full" and cached.identifiers.openalex_id:
        # OpenAlex abstract comes from inverted index, already reconstructed
        abstract_text = cached.abstract.teaser
        source_provider = "openalex"

    return GetAbstractOutput(
        work_key=work_key,
        mode=mode,
        abstract_text=abstract_text,
        source_provider=source_provider,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: get_fulltext_links
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_fulltext_links(work_key: str) -> dict:
    """Get fulltext and OA links for a work."""
    cached = _WORK_CACHE.get(work_key)
    if not cached:
        from scholarly_gateway.models import Access, Links
        return GetFulltextLinksOutput(
            work_key=work_key,
            links=Links(),
            access=Access(),
        ).model_dump()

    return GetFulltextLinksOutput(
        work_key=work_key,
        links=cached.links,
        access=cached.access,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: forward_citations
# ---------------------------------------------------------------------------

@mcp.tool()
async def forward_citations(
    work_key: str,
    limit: int = 10,
    cursor: Optional[str] = None,
) -> dict:
    """Get works that cite the given work (forward citations).

    Uses OpenAlex. arXiv is not_supported for citation data.
    """
    limit = min(limit, 25)
    cached = _WORK_CACHE.get(work_key)

    oa_works: list[InternalWork] = []
    oa_status = ProviderStatus(status="not_supported")
    oa_next_cursor: Optional[str] = None

    if cached and cached.identifiers.openalex_id:
        cursor_data = _decode_cursor(cursor) if cursor else {}
        oa_cursor = cursor_data.get("openalex")
        try:
            oa_works, oa_next_cursor, oa_status = await openalex_provider.fetch_citations(
                cached.identifiers.openalex_id,
                limit=limit,
                cursor=oa_cursor,
            )
        except Exception as e:
            oa_status = ProviderStatus(status="error", message=str(e))
    elif cached:
        oa_status = ProviderStatus(
            status="error",
            message="No OpenAlex ID available for citation lookup",
        )

    _cache_works(oa_works)

    next_cursor: Optional[str] = None
    if oa_next_cursor:
        next_cursor = _encode_cursor({"openalex": oa_next_cursor})

    provider_status = {
        "openalex": oa_status,
        "arxiv": _not_supported_status(),
    }

    md = render_citations_list(work_key, oa_works, "forward citations")
    return CitationsOutput(
        work_key=work_key,
        results=oa_works,
        markdown=md,
        next_cursor=next_cursor,
        provider_status=provider_status,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: backward_references
# ---------------------------------------------------------------------------

@mcp.tool()
async def backward_references(
    work_key: str,
    limit: int = 10,
    cursor: Optional[str] = None,
) -> dict:
    """Get works referenced by the given work (backward references).

    Uses OpenAlex. arXiv is not_supported for reference data.
    """
    limit = min(limit, 25)
    cached = _WORK_CACHE.get(work_key)

    oa_works: list[InternalWork] = []
    oa_status = ProviderStatus(status="not_supported")
    oa_next_cursor: Optional[str] = None

    if cached and cached.identifiers.openalex_id:
        cursor_data = _decode_cursor(cursor) if cursor else {}
        oa_cursor = cursor_data.get("openalex")
        try:
            oa_works, oa_next_cursor, oa_status = await openalex_provider.fetch_references(
                cached.identifiers.openalex_id,
                limit=limit,
                cursor=oa_cursor,
            )
        except Exception as e:
            oa_status = ProviderStatus(status="error", message=str(e))
    elif cached:
        oa_status = ProviderStatus(
            status="error",
            message="No OpenAlex ID available for reference lookup",
        )

    _cache_works(oa_works)

    next_cursor: Optional[str] = None
    if oa_next_cursor:
        next_cursor = _encode_cursor({"openalex": oa_next_cursor})

    provider_status = {
        "openalex": oa_status,
        "arxiv": _not_supported_status(),
    }

    md = render_citations_list(work_key, oa_works, "backward references")
    return CitationsOutput(
        work_key=work_key,
        results=oa_works,
        markdown=md,
        next_cursor=next_cursor,
        provider_status=provider_status,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: export_citation
# ---------------------------------------------------------------------------

@mcp.tool()
async def export_citation(
    work_key: str,
    format: Literal["bibtex", "ris", "csl-json"] = "bibtex",
) -> dict:
    """Export citation in BibTeX, RIS, or CSL-JSON format."""
    cached = _WORK_CACHE.get(work_key)
    if not cached:
        return ExportCitationOutput(
            work_key=work_key,
            format=format,
            citation_text=f"% Work {work_key} not found in cache",
        ).model_dump()

    bib = cached.bibliographic
    ids = cached.identifiers
    authors = bib.authors_preview
    year = bib.publication_year or ""
    title = bib.title
    venue = bib.venue or ""
    doi = ids.doi or ""

    # Generate a stable cite key
    first_author_last = (authors[0].split()[-1] if authors else "Unknown").lower()
    cite_key = f"{first_author_last}{year}"

    if format == "bibtex":
        kind_map = {
            "journal-article": "@article",
            "preprint": "@misc",
            "conference-paper": "@inproceedings",
            "other": "@misc",
        }
        entry_type = kind_map.get(cached.kind, "@misc")
        author_bibtex = " and ".join(authors)
        lines = [
            f"{entry_type}{{{cite_key},",
            f"  title = {{{{{title}}}}},",
            f"  author = {{{author_bibtex}}},",
        ]
        if year:
            lines.append(f"  year = {{{year}}},")
        if venue and cached.kind == "journal-article":
            lines.append(f"  journal = {{{venue}}},")
        elif venue and cached.kind == "conference-paper":
            lines.append(f"  booktitle = {{{venue}}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        if ids.arxiv_id:
            lines.append(f"  eprint = {{{ids.arxiv_id}}},")
            lines.append("  archivePrefix = {arXiv},")
        lines.append("}")
        citation_text = "\n".join(lines)

    elif format == "ris":
        type_map = {
            "journal-article": "JOUR",
            "preprint": "UNPB",
            "conference-paper": "CONF",
            "other": "GEN",
        }
        ris_type = type_map.get(cached.kind, "GEN")
        lines = [f"TY  - {ris_type}"]
        lines.append(f"TI  - {title}")
        for a in authors:
            lines.append(f"AU  - {a}")
        if year:
            lines.append(f"PY  - {year}")
        if venue:
            lines.append(f"JO  - {venue}")
        if doi:
            lines.append(f"DO  - {doi}")
        if ids.arxiv_id:
            lines.append(f"UR  - https://arxiv.org/abs/{ids.arxiv_id}")
        lines.append("ER  - ")
        citation_text = "\n".join(lines)

    else:  # csl-json
        csl: dict[str, Any] = {
            "id": cite_key,
            "type": cached.kind,
            "title": title,
            "author": [{"literal": a} for a in authors],
        }
        if year:
            csl["issued"] = {"date-parts": [[year]]}
        if venue:
            csl["container-title"] = venue
        if doi:
            csl["DOI"] = doi
        if ids.arxiv_id:
            csl["number"] = ids.arxiv_id
        import json as _json
        citation_text = _json.dumps(csl, indent=2)

    return ExportCitationOutput(
        work_key=work_key,
        format=format,
        citation_text=citation_text,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: compare_versions
# ---------------------------------------------------------------------------

@mcp.tool()
async def compare_versions(work_key: str) -> dict:
    """Compare versions of an arXiv preprint.

    Returns version list and a diff summary in markdown.
    """
    cached = _WORK_CACHE.get(work_key)

    if not cached or not cached.identifiers.arxiv_id:
        no_versions = CompareVersionsOutput(
            work_key=work_key,
            versions=[],
            diff_summary_markdown=f"_No arXiv ID found for `{work_key}`. Version comparison requires an arXiv paper._",
        )
        return no_versions.model_dump()

    arxiv_id = cached.identifiers.arxiv_id
    raw_versions, status = await arxiv_provider.fetch_versions(arxiv_id)

    if status.status != "ok" or not raw_versions:
        return CompareVersionsOutput(
            work_key=work_key,
            versions=[],
            diff_summary_markdown=f"_Could not fetch version data: {status.message}_",
        ).model_dump()

    versions = [
        VersionEntry(
            version=v.get("version", "v1"),
            submitted=v.get("submitted"),
            doi=v.get("doi"),
            journal_ref=v.get("journal_ref"),
        )
        for v in raw_versions
    ]

    # Build diff summary markdown
    lines = [f"### Version history for `{arxiv_id}`", ""]
    for v in versions:
        line = f"- **{v.version}**"
        if v.submitted:
            line += f" — submitted {v.submitted[:10]}"
        if v.doi:
            line += f" — DOI: [{v.doi}](https://doi.org/{v.doi})"
        if v.journal_ref:
            line += f" — Published: {v.journal_ref}"
        lines.append(line)

    has_doi = any(v.doi for v in versions)
    has_journal = any(v.journal_ref for v in versions)
    lines.append("")
    if has_doi:
        lines.append("**Status:** DOI present — likely has a VoR (Version of Record).")
    elif has_journal:
        lines.append("**Status:** Journal reference present — may have a published version.")
    else:
        lines.append("**Status:** No DOI or journal reference — preprint only.")

    return CompareVersionsOutput(
        work_key=work_key,
        versions=versions,
        diff_summary_markdown="\n".join(lines),
    ).model_dump()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
