"""arXiv provider: search and fetch via Atom feed API."""
from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from scholarly_gateway.identity import (
    generate_cluster_key,
    generate_work_key,
    normalize_arxiv_id,
    normalize_doi,
)
from scholarly_gateway.models import (
    AbstractInfo,
    Access,
    Bibliographic,
    Identifiers,
    InternalWork,
    Links,
    MetricsPreview,
    Provenance,
    ProvenanceRecord,
    ProviderStatus,
    WorkStatus,
)

_BASE_URL = "http://export.arxiv.org/api/query"
_TIMEOUT = 10.0
# arXiv: max_concurrency=1 with minimum inter-request interval
_SEMAPHORE = asyncio.Semaphore(1)
_MIN_INTERVAL = 3.0  # seconds between requests
_last_request_time: float = 0.0

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    return (el.text or "").strip() or None


def _parse_entry(entry: ET.Element) -> InternalWork:
    """Parse a single Atom <entry> element into InternalWork."""
    # ID / arXiv ID
    id_el = entry.find("atom:id", _NS)
    id_url = _text(id_el) or ""
    arxiv_id_norm, version = normalize_arxiv_id(id_url)

    # DOI
    doi_el = entry.find("arxiv:doi", _NS)
    doi = normalize_doi(_text(doi_el))

    # Title
    title_el = entry.find("atom:title", _NS)
    title = re.sub(r"\s+", " ", (_text(title_el) or "Untitled"))

    # Authors (up to 3 for preview)
    authors_preview: list[str] = []
    for author_el in entry.findall("atom:author", _NS)[:3]:
        name_el = author_el.find("atom:name", _NS)
        name = _text(name_el)
        if name:
            authors_preview.append(name)
    first_author = authors_preview[0] if authors_preview else None

    # Published / updated dates
    published_el = entry.find("atom:published", _NS)
    published_str = _text(published_el)  # e.g. "2021-01-29T18:00:00Z"
    year: Optional[int] = None
    pub_date: Optional[str] = None
    if published_str:
        try:
            dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            year = dt.year
            pub_date = dt.date().isoformat()
        except ValueError:
            pass

    # Abstract
    summary_el = entry.find("atom:summary", _NS)
    abstract_text = re.sub(r"\s+", " ", (_text(summary_el) or "")).strip() or None
    teaser = (abstract_text[:300] + "…") if abstract_text and len(abstract_text) > 300 else abstract_text

    # Links
    pdf_url: Optional[str] = None
    landing_url: Optional[str] = None
    for link_el in entry.findall("atom:link", _NS):
        rel = link_el.get("rel", "")
        href = link_el.get("href", "")
        title_attr = link_el.get("title", "")
        if title_attr == "pdf":
            pdf_url = href
        elif rel == "alternate":
            landing_url = href

    arxiv_abs_url = f"https://arxiv.org/abs/{arxiv_id_norm}" if arxiv_id_norm else None

    # Journal ref (indicates peer-reviewed)
    journal_ref_el = entry.find("arxiv:journal_ref", _NS)
    journal_ref = _text(journal_ref_el)

    review_status = "peer-reviewed" if journal_ref else "preprint"

    # Categories
    primary_category_el = entry.find("arxiv:primary_category", _NS)
    venue: Optional[str] = None
    if journal_ref:
        venue = journal_ref
    elif primary_category_el is not None:
        venue = primary_category_el.get("term")

    work_key, key_strength = generate_work_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id_norm,
        title=title,
        first_author=first_author,
        year=year,
    )
    cluster_key, _ = generate_cluster_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id_norm,
        title=title,
        first_author=first_author,
        year=year,
    )

    record_id = arxiv_id_norm or id_url

    return InternalWork(
        work_key=work_key,
        cluster_key=cluster_key,
        key_strength=key_strength,  # type: ignore[arg-type]
        kind="preprint",
        identifiers=Identifiers(
            doi=doi,
            arxiv_id=arxiv_id_norm,
            openalex_id=None,
        ),
        bibliographic=Bibliographic(
            title=title,
            authors_preview=authors_preview,
            publication_year=year,
            publication_date=pub_date,
            venue=venue,
        ),
        status=WorkStatus(
            review_status=review_status,  # type: ignore[arg-type]
            status_source="arxiv",
        ),
        abstract=AbstractInfo(
            teaser=teaser,
            has_full=bool(abstract_text),
        ),
        links=Links(
            landing_url=landing_url,
            pdf_url=pdf_url,
            doi_url=f"https://doi.org/{doi}" if doi else None,
            arxiv_abs_url=arxiv_abs_url,
        ),
        access=Access(
            is_open_access=True,  # arXiv is always open access
            best_oa_url=arxiv_abs_url,
        ),
        metrics_preview=MetricsPreview(cited_by_count=None),
        provenance=Provenance(records=[
            ProvenanceRecord(
                provider="arxiv",
                record_id=record_id or "unknown",
                source_url=landing_url or arxiv_abs_url,
                fetched_at=_now_iso(),
                match_basis="id",
                confidence=1.0,
            )
        ]),
    )


async def _get(url: str, params: dict) -> tuple[str, ProviderStatus]:
    """Make a rate-limited GET request to arXiv API."""
    global _last_request_time

    async with _SEMAPHORE:
        # Enforce minimum inter-request interval
        elapsed = time.monotonic() - _last_request_time
        if elapsed < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - elapsed)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=_TIMEOUT)
        except httpx.TimeoutException:
            return "", ProviderStatus(status="timeout", message="arXiv request timed out")
        except httpx.RequestError as e:
            return "", ProviderStatus(status="error", message=str(e))
        finally:
            _last_request_time = time.monotonic()

    if resp.status_code == 429:
        return "", ProviderStatus(
            status="rate_limited",
            http_status=429,
            message="Rate limited by arXiv",
            retry_after_seconds=30,
        )
    if resp.status_code >= 500:
        return "", ProviderStatus(
            status="error",
            http_status=resp.status_code,
            message=f"arXiv server error {resp.status_code}",
        )
    if resp.status_code != 200:
        return "", ProviderStatus(
            status="error",
            http_status=resp.status_code,
            message=f"Unexpected status {resp.status_code}",
        )
    return resp.text, ProviderStatus(status="ok", http_status=200)


def _parse_feed(xml_text: str) -> list[InternalWork]:
    """Parse arXiv Atom feed XML into list of InternalWork."""
    root = ET.fromstring(xml_text)
    works: list[InternalWork] = []
    for entry in root.findall("atom:entry", _NS):
        try:
            works.append(_parse_entry(entry))
        except Exception:
            pass  # skip malformed entries
    return works


def _build_search_query(query: str, filters: dict) -> str:
    """Build arXiv search query string."""
    # arXiv search: wrap in all: if no field specifier
    if not any(c in query for c in (":", "AND", "OR")):
        q = f"all:{query}"
    else:
        q = query
    return q


async def search(
    query: str,
    filters: dict,
    sort: str = "relevance",
    limit: int = 10,
    start: int = 0,
) -> tuple[list[InternalWork], Optional[int], ProviderStatus]:
    """Search arXiv. Returns (works, next_start, status).

    next_start is the integer offset for the next page (None if no more results).
    """
    sort_by = "relevance"
    sort_order = "descending"
    if sort == "recency":
        sort_by = "submittedDate"
        sort_order = "descending"
    elif sort == "citations":
        # arXiv API does not support citation-based sort; fall back to relevance
        sort_by = "relevance"

    params: dict[str, Any] = {
        "search_query": _build_search_query(query, filters),
        "start": start,
        "max_results": min(limit, 25),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    xml_text, status = await _get(_BASE_URL, params)
    if status.status != "ok" or not xml_text:
        return [], None, status

    works = _parse_feed(xml_text)

    # Determine next_start
    next_start: Optional[int] = None
    if len(works) == params["max_results"]:
        next_start = start + len(works)

    # Apply year filters post-hoc (arXiv API does not support year range natively)
    year_from = filters.get("year_from")
    year_to = filters.get("year_to")
    if year_from or year_to:
        filtered = []
        for w in works:
            y = w.bibliographic.publication_year
            if y is None:
                continue
            if year_from and y < year_from:
                continue
            if year_to and y > year_to:
                continue
            filtered.append(w)
        works = filtered

    return works, next_start, status


async def fetch_work(arxiv_id: str) -> tuple[Optional[InternalWork], ProviderStatus]:
    """Fetch a single arXiv work by arXiv ID."""
    arxiv_id_norm, _ = normalize_arxiv_id(arxiv_id)
    if not arxiv_id_norm:
        return None, ProviderStatus(status="error", message=f"Invalid arXiv ID: {arxiv_id}")

    params = {"id_list": arxiv_id_norm, "max_results": 1}
    xml_text, status = await _get(_BASE_URL, params)
    if status.status != "ok" or not xml_text:
        return None, status

    works = _parse_feed(xml_text)
    if not works:
        return None, ProviderStatus(status="error", message=f"arXiv ID not found: {arxiv_id_norm}")
    return works[0], status


async def fetch_versions(arxiv_id: str) -> tuple[list[dict], ProviderStatus]:
    """Fetch version history for an arXiv paper (from the abs page via API).

    Returns list of version dicts with 'version', 'submitted', optional 'doi', 'journal_ref'.
    """
    arxiv_id_norm, _ = normalize_arxiv_id(arxiv_id)
    if not arxiv_id_norm:
        return [], ProviderStatus(status="error", message=f"Invalid arXiv ID: {arxiv_id}")

    # Fetch all versions by not specifying a version number
    params = {"id_list": arxiv_id_norm, "max_results": 1}
    xml_text, status = await _get(_BASE_URL, params)
    if status.status != "ok" or not xml_text:
        return [], status

    # Parse versioning info from Atom feed
    root = ET.fromstring(xml_text)
    versions: list[dict] = []

    for entry in root.findall("atom:entry", _NS):
        doi_el = entry.find("arxiv:doi", _NS)
        doi = normalize_doi(_text(doi_el))
        journal_ref_el = entry.find("arxiv:journal_ref", _NS)
        journal_ref = _text(journal_ref_el)
        published_el = entry.find("atom:published", _NS)
        updated_el = entry.find("atom:updated", _NS)

        # arXiv API returns only current version in the feed
        # We simulate "v1" from published and current version from updated
        published = _text(published_el)
        updated = _text(updated_el)

        id_el = entry.find("atom:id", _NS)
        id_url = _text(id_el) or ""
        _, version_tag = normalize_arxiv_id(id_url)

        v_entry: dict = {
            "version": version_tag or "v1",
            "submitted": published,
            "doi": doi,
            "journal_ref": journal_ref,
        }
        versions.append(v_entry)
        if updated and updated != published:
            versions.append({"version": "latest", "submitted": updated, "doi": doi, "journal_ref": journal_ref})

    return versions, status
