"""OpenAlex provider: search, fetch by ID, citations/references."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from scholarly_gateway.identity import (
    generate_cluster_key,
    generate_work_key,
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

_BASE_URL = "https://api.openalex.org"
_TIMEOUT = 10.0
_MAX_CONCURRENCY = 5
_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENCY)

# Exponential backoff state per process
_backoff_until: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reconstruct_abstract(inverted_index: dict[str, list[int]]) -> str:
    """Reconstruct abstract text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    max_pos = max(pos for positions in inverted_index.values() for pos in positions)
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(w for w in words if w)


def _map_type(oa_type: Optional[str]) -> str:
    mapping = {
        "journal-article": "journal-article",
        "preprint": "preprint",
        "conference-paper": "conference-paper",
        "posted-content": "preprint",
        "book-chapter": "other",
        "book": "other",
        "dataset": "other",
        "dissertation": "other",
    }
    return mapping.get(oa_type or "", "other")


def _parse_work(raw: dict[str, Any]) -> InternalWork:
    """Parse a single OpenAlex work dict into InternalWork."""
    oa_id: str = raw.get("id", "")
    doi_raw = raw.get("doi")
    doi = normalize_doi(doi_raw)

    # arXiv ID from locations or primary_location
    arxiv_id: Optional[str] = None
    for loc in raw.get("locations", []):
        src = loc.get("source") or {}
        if "arxiv" in (src.get("host_organization_lineage_names") or []):
            landing = loc.get("landing_page_url") or ""
            if "arxiv.org" in landing:
                from scholarly_gateway.identity import normalize_arxiv_id
                aid, _ = normalize_arxiv_id(landing)
                if aid:
                    arxiv_id = aid
                    break

    # Authors (up to 3 for preview)
    authorships = raw.get("authorships", [])
    authors_preview: list[str] = []
    for a in authorships[:3]:
        author_obj = a.get("author") or {}
        name = author_obj.get("display_name") or ""
        if name:
            authors_preview.append(name)

    first_author = authors_preview[0] if authors_preview else None

    work_key, key_strength = generate_work_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id,
        title=raw.get("title") or "",
        first_author=first_author,
        year=raw.get("publication_year"),
    )
    cluster_key, _ = generate_cluster_key(
        doi_norm=doi,
        arxiv_id_norm=arxiv_id,
        title=raw.get("title") or "",
        first_author=first_author,
        year=raw.get("publication_year"),
    )

    # Abstract
    inv_index = raw.get("abstract_inverted_index") or {}
    abstract_text = _reconstruct_abstract(inv_index) if inv_index else None
    teaser = (abstract_text[:300] + "…") if abstract_text and len(abstract_text) > 300 else abstract_text

    # Best OA URL
    best_oa = raw.get("best_oa_location") or {}
    best_oa_url = best_oa.get("pdf_url") or best_oa.get("landing_page_url")

    # Primary location PDF
    primary = raw.get("primary_location") or {}
    pdf_url = primary.get("pdf_url")
    landing_url = primary.get("landing_page_url")

    # Review status
    oa_type = raw.get("type") or ""
    if oa_type == "preprint" or oa_type == "posted-content":
        review_status = "preprint"
    elif oa_type == "journal-article":
        review_status = "peer-reviewed"
    else:
        review_status = "unknown"

    # cited_by_count
    cited_by = raw.get("cited_by_count")

    return InternalWork(
        work_key=work_key,
        cluster_key=cluster_key,
        key_strength=key_strength,  # type: ignore[arg-type]
        kind=_map_type(oa_type),  # type: ignore[arg-type]
        identifiers=Identifiers(
            doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=oa_id or None,
        ),
        bibliographic=Bibliographic(
            title=raw.get("title") or "Untitled",
            authors_preview=authors_preview,
            publication_year=raw.get("publication_year"),
            publication_date=raw.get("publication_date"),
            venue=((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
        ),
        status=WorkStatus(
            review_status=review_status,  # type: ignore[arg-type]
            status_source="openalex",
        ),
        abstract=AbstractInfo(
            teaser=teaser,
            has_full=bool(abstract_text),
        ),
        links=Links(
            landing_url=landing_url,
            pdf_url=pdf_url,
            doi_url=f"https://doi.org/{doi}" if doi else None,
            arxiv_abs_url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
        ),
        access=Access(
            is_open_access=bool(raw.get("open_access", {}).get("is_oa")),
            best_oa_url=best_oa_url,
        ),
        metrics_preview=MetricsPreview(cited_by_count=cited_by),
        provenance=Provenance(records=[
            ProvenanceRecord(
                provider="openalex",
                record_id=oa_id,
                source_url=oa_id or None,
                fetched_at=_now_iso(),
                match_basis="id",
                confidence=1.0,
            )
        ]),
    )


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> tuple[dict, ProviderStatus]:
    """Make a GET request with backoff/rate-limit handling."""
    global _backoff_until
    now = time.monotonic()
    if now < _backoff_until:
        await asyncio.sleep(_backoff_until - now)

    async with _SEMAPHORE:
        try:
            resp = await client.get(url, params=params, timeout=_TIMEOUT)
        except httpx.TimeoutException:
            return {}, ProviderStatus(status="timeout", message="Request timed out")
        except httpx.RequestError as e:
            return {}, ProviderStatus(status="error", message=str(e))

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "5"))
        _backoff_until = time.monotonic() + retry_after
        return {}, ProviderStatus(
            status="rate_limited",
            http_status=429,
            message="Rate limited by OpenAlex",
            retry_after_seconds=retry_after,
        )
    if resp.status_code >= 500:
        return {}, ProviderStatus(
            status="error",
            http_status=resp.status_code,
            message=f"Server error {resp.status_code}",
        )
    if resp.status_code != 200:
        return {}, ProviderStatus(
            status="error",
            http_status=resp.status_code,
            message=f"Unexpected status {resp.status_code}",
        )

    return resp.json(), ProviderStatus(status="ok", http_status=200)


async def search(
    query: str,
    filters: dict,
    sort: str = "relevance",
    limit: int = 10,
    cursor: Optional[str] = None,
) -> tuple[list[InternalWork], Optional[str], ProviderStatus]:
    """Search OpenAlex works. Returns (works, next_cursor, status)."""
    params: dict[str, Any] = {
        "search": query,
        "per_page": min(limit, 25),
        "select": (
            "id,doi,title,publication_year,publication_date,type,"
            "authorships,abstract_inverted_index,primary_location,"
            "best_oa_location,open_access,cited_by_count,locations"
        ),
    }
    if cursor:
        params["cursor"] = cursor
    else:
        params["cursor"] = "*"

    # Filters
    filter_parts: list[str] = []
    if filters.get("year_from"):
        filter_parts.append(f"publication_year:>{filters['year_from'] - 1}")
    if filters.get("year_to"):
        filter_parts.append(f"publication_year:<{filters['year_to'] + 1}")
    if filters.get("oa_only"):
        filter_parts.append("is_oa:true")
    if filters.get("kind"):
        filter_parts.append(f"type:{filters['kind']}")
    if filter_parts:
        params["filter"] = ",".join(filter_parts)

    # Sort
    if sort == "recency":
        params["sort"] = "publication_date:desc"
    elif sort == "citations":
        params["sort"] = "cited_by_count:desc"
    # relevance = default (no sort param)

    async with httpx.AsyncClient() as client:
        data, status = await _get(client, f"{_BASE_URL}/works", params)

    if status.status != "ok":
        return [], None, status

    results = data.get("results", [])
    meta = data.get("meta", {})
    next_cursor = meta.get("next_cursor")

    works = [_parse_work(r) for r in results]
    return works, next_cursor, status


async def fetch_work(openalex_id: str) -> tuple[Optional[InternalWork], ProviderStatus]:
    """Fetch a single work by OpenAlex ID."""
    # Strip base URL if present
    work_id = openalex_id.replace("https://openalex.org/", "")
    params = {
        "select": (
            "id,doi,title,publication_year,publication_date,type,"
            "authorships,abstract_inverted_index,primary_location,"
            "best_oa_location,open_access,cited_by_count,locations"
        )
    }
    async with httpx.AsyncClient() as client:
        data, status = await _get(client, f"{_BASE_URL}/works/{work_id}", params)

    if status.status != "ok" or not data:
        return None, status

    return _parse_work(data), status


async def fetch_citations(
    openalex_id: str,
    limit: int = 10,
    cursor: Optional[str] = None,
) -> tuple[list[InternalWork], Optional[str], ProviderStatus]:
    """Fetch works that cite the given OpenAlex work (forward citations)."""
    work_id = openalex_id.replace("https://openalex.org/", "")
    params: dict[str, Any] = {
        "filter": f"cites:{work_id}",
        "per_page": min(limit, 25),
        "select": (
            "id,doi,title,publication_year,publication_date,type,"
            "authorships,primary_location,best_oa_location,"
            "open_access,cited_by_count,locations"
        ),
        "cursor": cursor or "*",
    }
    async with httpx.AsyncClient() as client:
        data, status = await _get(client, f"{_BASE_URL}/works", params)

    if status.status != "ok":
        return [], None, status

    results = data.get("results", [])
    meta = data.get("meta", {})
    works = [_parse_work(r) for r in results]
    return works, meta.get("next_cursor"), status


async def fetch_references(
    openalex_id: str,
    limit: int = 10,
    cursor: Optional[str] = None,
) -> tuple[list[InternalWork], Optional[str], ProviderStatus]:
    """Fetch referenced works (backward references) for the given OpenAlex work."""
    work_id = openalex_id.replace("https://openalex.org/", "")
    params: dict[str, Any] = {
        "filter": f"cited_by:{work_id}",
        "per_page": min(limit, 25),
        "select": (
            "id,doi,title,publication_year,publication_date,type,"
            "authorships,primary_location,best_oa_location,"
            "open_access,cited_by_count,locations"
        ),
        "cursor": cursor or "*",
    }
    async with httpx.AsyncClient() as client:
        data, status = await _get(client, f"{_BASE_URL}/works", params)

    if status.status != "ok":
        return [], None, status

    results = data.get("results", [])
    meta = data.get("meta", {})
    works = [_parse_work(r) for r in results]
    return works, meta.get("next_cursor"), status
