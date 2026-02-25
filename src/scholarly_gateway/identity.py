"""ID normalization, work_key/cluster_key generation, and merge/link logic."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

from scholarly_gateway.models import InternalWork, LinkedCandidate

# ---------------------------------------------------------------------------
# DOI normalization
# ---------------------------------------------------------------------------

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


def normalize_doi(raw: Optional[str]) -> Optional[str]:
    """Return lowercase DOI with leading resolver/prefix stripped."""
    if not raw:
        return None
    doi = raw.strip()
    for prefix in _DOI_PREFIXES:
        if doi.lower().startswith(prefix.lower()):
            doi = doi[len(prefix):]
            break
    doi = doi.strip().lower()
    return doi if doi else None


# ---------------------------------------------------------------------------
# arXiv ID normalization
# ---------------------------------------------------------------------------

# New-style: YYMM.NNNNN or YYMM.NNNNNN (with optional vN suffix)
_ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,6})(?:v(\d+))?$")
# Old-style: category/YYMMNNN (with optional vN suffix)
_ARXIV_OLD = re.compile(r"^([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v(\d+))?$")
# Strip common URL prefixes
_ARXIV_URL_PREFIXES = (
    "https://arxiv.org/abs/",
    "http://arxiv.org/abs/",
    "https://arxiv.org/pdf/",
    "http://arxiv.org/pdf/",
    "arxiv:",
)


def normalize_arxiv_id(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (canonical_id, version_str) with version stripped from canonical_id.

    canonical_id is the bare arXiv ID without version suffix.
    version_str is e.g. "v2" or None.
    """
    if not raw:
        return None, None
    s = raw.strip()
    for prefix in _ARXIV_URL_PREFIXES:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):]
            break
    s = s.strip().rstrip("/")

    m = _ARXIV_NEW.match(s)
    if m:
        return m.group(1), (f"v{m.group(2)}" if m.group(2) else None)

    m = _ARXIV_OLD.match(s)
    if m:
        return m.group(1), (f"v{m.group(2)}" if m.group(2) else None)

    return None, None


# ---------------------------------------------------------------------------
# Stable key generation
# ---------------------------------------------------------------------------

def _sha256_prefix(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _normalize_title(title: str) -> str:
    """Lowercase, remove punctuation/accents for fallback keying."""
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", ascii_only.lower()).strip()


def generate_work_key(
    doi_norm: Optional[str] = None,
    arxiv_id_norm: Optional[str] = None,
    title: Optional[str] = None,
    first_author: Optional[str] = None,
    year: Optional[int] = None,
) -> tuple[str, str]:
    """Return (work_key, key_strength).

    Priority: doi_norm > arxiv_id_norm > title+author+year fallback.
    """
    if doi_norm:
        return f"wrk_{_sha256_prefix('doi:' + doi_norm)}", "strong"
    if arxiv_id_norm:
        return f"wrk_{_sha256_prefix('arxiv:' + arxiv_id_norm)}", "strong"
    # Weak fallback
    parts = [
        _normalize_title(title or ""),
        (first_author or "").lower().strip(),
        str(year or ""),
    ]
    combined = "|".join(parts)
    return f"wrk_{_sha256_prefix('weak:' + combined)}", "weak"


def generate_cluster_key(
    doi_norm: Optional[str] = None,
    arxiv_id_norm: Optional[str] = None,
    title: Optional[str] = None,
    first_author: Optional[str] = None,
    year: Optional[int] = None,
) -> tuple[str, str]:
    """Return (cluster_key, cluster_strength).

    Priority: doi_norm > arxiv_id_norm > weak fallback.
    """
    if doi_norm:
        return f"clu_{_sha256_prefix('doi:' + doi_norm)}", "strong"
    if arxiv_id_norm:
        return f"clu_{_sha256_prefix('arxiv:' + arxiv_id_norm)}", "strong"
    parts = [
        _normalize_title(title or ""),
        (first_author or "").lower().strip(),
        str(year or ""),
    ]
    combined = "|".join(parts)
    return f"clu_{_sha256_prefix('weak:' + combined)}", "weak"


# ---------------------------------------------------------------------------
# Merge / link logic
# ---------------------------------------------------------------------------

def can_hard_merge(a: InternalWork, b: InternalWork) -> bool:
    """True iff works share at least one hard identifier."""
    # Same doi_norm
    if a.identifiers.doi and b.identifiers.doi:
        if a.identifiers.doi.lower() == b.identifiers.doi.lower():
            return True
    # Same arxiv_id_norm
    if a.identifiers.arxiv_id and b.identifiers.arxiv_id:
        if a.identifiers.arxiv_id == b.identifiers.arxiv_id:
            return True
    # Same openalex_id (within provider only — both must have it)
    if a.identifiers.openalex_id and b.identifiers.openalex_id:
        if a.identifiers.openalex_id == b.identifiers.openalex_id:
            return True
    return False


def hard_merge(primary: InternalWork, secondary: InternalWork) -> InternalWork:
    """Merge secondary into primary. Primary wins on conflicts.

    Provenance records from both are combined.
    """
    merged = primary.model_copy(deep=True)

    # Fill in missing identifiers from secondary
    if not merged.identifiers.doi and secondary.identifiers.doi:
        merged.identifiers.doi = secondary.identifiers.doi
    if not merged.identifiers.arxiv_id and secondary.identifiers.arxiv_id:
        merged.identifiers.arxiv_id = secondary.identifiers.arxiv_id
    if not merged.identifiers.openalex_id and secondary.identifiers.openalex_id:
        merged.identifiers.openalex_id = secondary.identifiers.openalex_id

    # Fill missing bibliographic fields
    if not merged.bibliographic.publication_date and secondary.bibliographic.publication_date:
        merged.bibliographic.publication_date = secondary.bibliographic.publication_date
    if not merged.bibliographic.venue and secondary.bibliographic.venue:
        merged.bibliographic.venue = secondary.bibliographic.venue

    # Fill missing links
    if not merged.links.pdf_url and secondary.links.pdf_url:
        merged.links.pdf_url = secondary.links.pdf_url
    if not merged.links.landing_url and secondary.links.landing_url:
        merged.links.landing_url = secondary.links.landing_url
    if not merged.links.arxiv_abs_url and secondary.links.arxiv_abs_url:
        merged.links.arxiv_abs_url = secondary.links.arxiv_abs_url

    # Fill missing access
    if not merged.access.best_oa_url and secondary.access.best_oa_url:
        merged.access.best_oa_url = secondary.access.best_oa_url
    if secondary.access.is_open_access:
        merged.access.is_open_access = True

    # Combine provenance records (dedup by provider+record_id)
    existing_ids = {(r.provider, r.record_id) for r in merged.provenance.records}
    for rec in secondary.provenance.records:
        if (rec.provider, rec.record_id) not in existing_ids:
            merged.provenance.records.append(rec)

    # Fill abstract teaser if missing
    if not merged.abstract.teaser and secondary.abstract.teaser:
        merged.abstract.teaser = secondary.abstract.teaser
    if secondary.abstract.has_full:
        merged.abstract.has_full = True

    # Upgrade key strength if secondary is stronger
    if merged.key_strength == "weak" and secondary.key_strength == "strong":
        merged.work_key = secondary.work_key
        merged.cluster_key = secondary.cluster_key
        merged.key_strength = "strong"

    return merged


def soft_link(works: list[InternalWork]) -> list[InternalWork]:
    """Add linked_candidates between works that share no hard IDs but look similar.

    V1: uses exact title match as a simple similarity heuristic.
    Works are never collapsed — they remain separate with references.
    """
    if len(works) <= 1:
        return works

    def _title_key(w: InternalWork) -> str:
        return _normalize_title(w.bibliographic.title)

    groups: dict[str, list[int]] = {}
    for i, w in enumerate(works):
        tk = _title_key(w)
        if tk:
            groups.setdefault(tk, []).append(i)

    result = [w.model_copy(deep=True) for w in works]
    for indices in groups.values():
        if len(indices) < 2:
            continue
        for i in indices:
            for j in indices:
                if i == j:
                    continue
                target = works[j]
                candidate = LinkedCandidate(
                    work_key=target.work_key,
                    confidence=0.8,
                    basis="similarity",
                )
                existing_keys = {lc.work_key for lc in result[i].linked_candidates}
                if candidate.work_key not in existing_keys:
                    result[i].linked_candidates.append(candidate)
    return result


def merge_work_lists(lists: list[list[InternalWork]]) -> list[InternalWork]:
    """Merge multiple provider result lists using hard-merge rules.

    Works that cannot be hard-merged are returned separately.
    Soft-link pass runs at the end.
    """
    merged: list[InternalWork] = []

    for work_list in lists:
        for work in work_list:
            placed = False
            for i, existing in enumerate(merged):
                if can_hard_merge(existing, work):
                    merged[i] = hard_merge(existing, work)
                    placed = True
                    break
            if not placed:
                merged.append(work.model_copy(deep=True))

    return soft_link(merged)
