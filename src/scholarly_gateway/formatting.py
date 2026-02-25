"""Markdown rendering for InternalWork objects."""
from __future__ import annotations

from scholarly_gateway.models import InternalWork


def _authors_str(work: InternalWork) -> str:
    authors = work.bibliographic.authors_preview
    if not authors:
        return "Unknown"
    return "; ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")


def _year_str(work: InternalWork) -> str:
    y = work.bibliographic.publication_year
    return str(y) if y else "?"


def _venue_str(work: InternalWork) -> str:
    return work.bibliographic.venue or "—"


def _oa_badge(work: InternalWork) -> str:
    return "OA" if work.access.is_open_access else "—"


def _citations_str(work: InternalWork) -> str:
    c = work.metrics_preview.cited_by_count
    return str(c) if c is not None else "—"


def render_search_results(works: list[InternalWork]) -> str:
    """Render a list of InternalWork as a compact markdown table."""
    if not works:
        return "_No results found._"

    header = "| # | work_key | Title | Authors | Year | Venue | OA | Cites |\n"
    sep    = "|---|----------|-------|---------|------|-------|----|-------|\n"
    rows = []
    for idx, w in enumerate(works, 1):
        title = w.bibliographic.title.replace("|", "\\|")
        row = (
            f"| {idx} "
            f"| `{w.work_key}` "
            f"| {title} "
            f"| {_authors_str(w)} "
            f"| {_year_str(w)} "
            f"| {_venue_str(w)} "
            f"| {_oa_badge(w)} "
            f"| {_citations_str(w)} |"
        )
        rows.append(row)
    return header + sep + "\n".join(rows)


def render_work_detail(work: InternalWork) -> str:
    """Render a single InternalWork as markdown detail view."""
    lines = []
    title = work.bibliographic.title
    lines.append(f"## {title}")
    lines.append("")
    lines.append(f"**work_key:** `{work.work_key}`  ")
    lines.append(f"**cluster_key:** `{work.cluster_key}`  ")
    lines.append(f"**kind:** {work.kind}  ")
    lines.append(f"**review_status:** {work.status.review_status}  ")
    lines.append("")

    # Identifiers
    ids = work.identifiers
    if ids.doi:
        lines.append(f"**DOI:** [{ids.doi}](https://doi.org/{ids.doi})  ")
    if ids.arxiv_id:
        lines.append(f"**arXiv:** [{ids.arxiv_id}](https://arxiv.org/abs/{ids.arxiv_id})  ")
    if ids.openalex_id:
        lines.append(f"**OpenAlex:** [{ids.openalex_id}]({ids.openalex_id})  ")
    lines.append("")

    # Bibliographic
    bib = work.bibliographic
    lines.append(f"**Authors:** {_authors_str(work)}  ")
    lines.append(f"**Year:** {_year_str(work)}  ")
    if bib.publication_date:
        lines.append(f"**Date:** {bib.publication_date}  ")
    if bib.venue:
        lines.append(f"**Venue:** {bib.venue}  ")
    lines.append("")

    # Abstract teaser
    if work.abstract.teaser:
        lines.append("**Abstract (teaser):**")
        lines.append(f"> {work.abstract.teaser}")
        lines.append("")

    # Access / links
    lines.append("**Access:**")
    if work.access.is_open_access:
        oa_url = work.access.best_oa_url or work.links.landing_url or ""
        lines.append(f"- Open Access: [link]({oa_url})" if oa_url else "- Open Access")
    else:
        lines.append("- Restricted")
    if work.links.pdf_url:
        lines.append(f"- PDF: [{work.links.pdf_url}]({work.links.pdf_url})")
    lines.append("")

    # Metrics
    if work.metrics_preview.cited_by_count is not None:
        lines.append(f"**Cited by:** {work.metrics_preview.cited_by_count}")
        lines.append("")

    return "\n".join(lines)


def render_citations_list(work_key: str, works: list[InternalWork], direction: str) -> str:
    """Render forward citations or backward references as a table."""
    if not works:
        return f"_No {direction} found for `{work_key}`._"
    header_line = f"### {direction.title()} for `{work_key}`\n\n"
    return header_line + render_search_results(works)
