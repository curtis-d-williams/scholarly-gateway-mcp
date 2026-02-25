"""Pydantic v2 models for the Scholarly Gateway MCP V1 IDO schema."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models for InternalWork
# ---------------------------------------------------------------------------

class Identifiers(BaseModel):
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None


class Bibliographic(BaseModel):
    title: str
    authors_preview: list[str] = Field(default_factory=list)
    publication_year: Optional[int] = None
    publication_date: Optional[str] = None
    venue: Optional[str] = None


class WorkStatus(BaseModel):
    review_status: Literal["preprint", "peer-reviewed", "unknown"] = "unknown"
    status_source: Literal["arxiv", "openalex", "inferred"] = "inferred"


class AbstractInfo(BaseModel):
    teaser: Optional[str] = None
    has_full: bool = False


class Links(BaseModel):
    landing_url: Optional[str] = None
    pdf_url: Optional[str] = None
    doi_url: Optional[str] = None
    arxiv_abs_url: Optional[str] = None


class Access(BaseModel):
    is_open_access: bool = False
    best_oa_url: Optional[str] = None


class MetricsPreview(BaseModel):
    cited_by_count: Optional[int] = None


class ProvenanceRecord(BaseModel):
    provider: Literal["openalex", "arxiv"]
    record_id: str
    source_url: Optional[str] = None
    fetched_at: str  # ISO-8601
    match_basis: Literal["id", "doi", "arxiv_id", "similarity"] = "id"
    confidence: float = 1.0


class Provenance(BaseModel):
    records: list[ProvenanceRecord] = Field(default_factory=list)


class LinkedCandidate(BaseModel):
    work_key: str
    confidence: float
    basis: str = "similarity"


# ---------------------------------------------------------------------------
# Core IDO: InternalWork
# ---------------------------------------------------------------------------

class InternalWork(BaseModel):
    schema_version: str = "1.0"
    work_key: str
    cluster_key: str
    key_strength: Literal["strong", "weak"] = "strong"
    kind: Literal["journal-article", "preprint", "conference-paper", "other"] = "other"

    identifiers: Identifiers = Field(default_factory=Identifiers)
    bibliographic: Bibliographic
    status: WorkStatus = Field(default_factory=WorkStatus)
    abstract: AbstractInfo = Field(default_factory=AbstractInfo)
    links: Links = Field(default_factory=Links)
    access: Access = Field(default_factory=Access)
    metrics_preview: MetricsPreview = Field(default_factory=MetricsPreview)
    provenance: Provenance = Field(default_factory=Provenance)
    linked_candidates: list[LinkedCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Provider status
# ---------------------------------------------------------------------------

class ProviderStatus(BaseModel):
    status: Literal["ok", "timeout", "rate_limited", "auth_required", "error", "not_supported"] = "ok"
    http_status: Optional[int] = None
    message: str = ""
    retry_after_seconds: int = 0


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------

class SearchFilters(BaseModel):
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    kind: Optional[str] = None
    oa_only: bool = False
    providers: Optional[list[str]] = None


class SearchWorksOutput(BaseModel):
    schema_version: str = "1.0"
    results: list[InternalWork]
    markdown: str
    next_cursor: Optional[str] = None
    provider_status: dict[str, ProviderStatus]


class GetWorkOutput(BaseModel):
    schema_version: str = "1.0"
    work: InternalWork
    markdown: str
    provider_status: dict[str, ProviderStatus]


class GetAbstractOutput(BaseModel):
    work_key: str
    mode: Literal["teaser", "full"]
    abstract_text: Optional[str]
    source_provider: Optional[str]


class GetFulltextLinksOutput(BaseModel):
    work_key: str
    links: Links
    access: Access


class CitationsOutput(BaseModel):
    schema_version: str = "1.0"
    work_key: str
    results: list[InternalWork]
    markdown: str
    next_cursor: Optional[str] = None
    provider_status: dict[str, ProviderStatus]


class ExportCitationOutput(BaseModel):
    work_key: str
    format: Literal["bibtex", "ris", "csl-json"]
    citation_text: str


class VersionEntry(BaseModel):
    version: str
    submitted: Optional[str] = None
    doi: Optional[str] = None
    journal_ref: Optional[str] = None


class CompareVersionsOutput(BaseModel):
    work_key: str
    versions: list[VersionEntry]
    diff_summary_markdown: str
