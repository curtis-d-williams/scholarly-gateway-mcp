"""Offline conformance tests for the provider_status contract.

Validates the shape and invariants of ProviderStatus as defined in V1_CONTRACT.md
and implemented in scholarly_gateway.models.  No network calls are made.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from scholarly_gateway.models import (
    CitationsOutput,
    GetWorkOutput,
    ProviderStatus,
    SearchWorksOutput,
)
from scholarly_gateway.identity import generate_work_key, generate_cluster_key
from scholarly_gateway.models import Bibliographic, InternalWork


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All status values that V1 allows — derived directly from the Literal annotation
# on ProviderStatus.status rather than hard-coded strings.
_ALLOWED_STATUSES: tuple[str, ...] = tuple(
    ProviderStatus.model_fields["status"].annotation.__args__  # type: ignore[union-attr]
)


def _minimal_work() -> InternalWork:
    """Build a minimal InternalWork offline, without touching any provider."""
    wk, strength = generate_work_key(doi_norm="10.9999/test.0001")
    ck, _ = generate_cluster_key(doi_norm="10.9999/test.0001")
    return InternalWork(
        work_key=wk,
        cluster_key=ck,
        key_strength=strength,
        bibliographic=Bibliographic(title="Conformance Test Paper"),
    )


# ---------------------------------------------------------------------------
# TestProviderStatusModel — unit-level shape and invariant tests
# ---------------------------------------------------------------------------

class TestProviderStatusModel:
    """ProviderStatus model shape and field-level invariants."""

    def test_default_status_is_ok(self):
        ps = ProviderStatus()
        assert ps.status == "ok"

    def test_default_fields(self):
        ps = ProviderStatus()
        assert ps.http_status is None
        assert isinstance(ps.message, str)
        assert isinstance(ps.retry_after_seconds, int)
        assert ps.retry_after_seconds >= 0

    def test_all_allowed_statuses_accepted(self):
        for s in _ALLOWED_STATUSES:
            ps = ProviderStatus(status=s)
            assert ps.status == s

    def test_unknown_status_rejected(self):
        with pytest.raises(ValidationError):
            ProviderStatus(status="unknown_status_xyz")  # type: ignore[arg-type]

    def test_http_status_int_or_none(self):
        ps_none = ProviderStatus(http_status=None)
        assert ps_none.http_status is None

        ps_int = ProviderStatus(http_status=429)
        assert isinstance(ps_int.http_status, int)
        assert ps_int.http_status == 429

    def test_message_is_str(self):
        ps = ProviderStatus(message="Some error message")
        assert isinstance(ps.message, str)

    def test_message_default_is_empty_string(self):
        ps = ProviderStatus()
        assert ps.message == ""

    def test_retry_after_seconds_is_non_negative_int(self):
        ps = ProviderStatus(retry_after_seconds=60)
        assert isinstance(ps.retry_after_seconds, int)
        assert ps.retry_after_seconds >= 0

    def test_retry_after_seconds_zero_allowed(self):
        ps = ProviderStatus(retry_after_seconds=0)
        assert ps.retry_after_seconds == 0

    def test_not_supported_construction(self):
        """Pure offline construction of a not_supported status — mirrors _not_supported_status()."""
        ps = ProviderStatus(
            status="not_supported",
            message="Not supported by this provider in V1",
        )
        assert ps.status == "not_supported"
        assert isinstance(ps.message, str)
        assert ps.http_status is None
        assert ps.retry_after_seconds == 0

    def test_rate_limited_with_retry(self):
        ps = ProviderStatus(
            status="rate_limited",
            http_status=429,
            message="Too many requests",
            retry_after_seconds=30,
        )
        assert ps.status == "rate_limited"
        assert ps.http_status == 429
        assert ps.retry_after_seconds >= 0

    def test_model_dump_keys(self):
        """model_dump() must include the four canonical fields."""
        ps = ProviderStatus(status="ok")
        d = ps.model_dump()
        assert set(d.keys()) >= {"status", "http_status", "message", "retry_after_seconds"}

    def test_status_in_allowed_set_after_round_trip(self):
        """Status value must survive a model_dump / model_validate round-trip."""
        for s in _ALLOWED_STATUSES:
            ps = ProviderStatus(status=s)
            d = ps.model_dump()
            ps2 = ProviderStatus.model_validate(d)
            assert ps2.status == s
            assert ps2.status in _ALLOWED_STATUSES


# ---------------------------------------------------------------------------
# TestAllowedStatusDomain — derive the domain from the model
# ---------------------------------------------------------------------------

class TestAllowedStatusDomain:
    """The allowed status domain must match V1 expectations."""

    def test_not_supported_in_allowed_statuses(self):
        assert "not_supported" in _ALLOWED_STATUSES

    def test_ok_in_allowed_statuses(self):
        assert "ok" in _ALLOWED_STATUSES

    def test_error_in_allowed_statuses(self):
        assert "error" in _ALLOWED_STATUSES

    def test_no_extra_values_outside_model(self):
        """No status string outside the model's Literal is accepted."""
        for bad in ("success", "failed", "pending", "unknown", ""):
            with pytest.raises(ValidationError):
                ProviderStatus(status=bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestProviderStatusMapping — validate dict[str, ProviderStatus] contract
# ---------------------------------------------------------------------------

class TestProviderStatusMapping:
    """provider_status must be a mapping keyed by provider name."""

    def _make_search_output(
        self, provider_status: dict[str, ProviderStatus]
    ) -> SearchWorksOutput:
        return SearchWorksOutput(
            results=[],
            markdown="",
            provider_status=provider_status,
        )

    def test_keys_are_strings(self):
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(status="ok"),
        }
        out = self._make_search_output(ps_map)
        for k in out.provider_status:
            assert isinstance(k, str)

    def test_values_are_provider_status(self):
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(status="not_supported"),
        }
        out = self._make_search_output(ps_map)
        for v in out.provider_status.values():
            assert isinstance(v, ProviderStatus)

    def test_each_value_status_in_allowed_set(self):
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(status="not_supported"),
        }
        out = self._make_search_output(ps_map)
        for v in out.provider_status.values():
            assert v.status in _ALLOWED_STATUSES

    def test_not_supported_provider_in_mapping(self):
        """arXiv is not_supported for citation tools — verify that status is preserved."""
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(
                status="not_supported",
                message="Not supported by this provider in V1",
            ),
        }
        out = self._make_search_output(ps_map)
        assert out.provider_status["arxiv"].status == "not_supported"

    def test_model_dump_provider_status_serialisable(self):
        """model_dump() on an output object must include provider_status."""
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(status="not_supported"),
        }
        out = self._make_search_output(ps_map)
        d = out.model_dump()
        assert "provider_status" in d
        assert isinstance(d["provider_status"], dict)
        for v in d["provider_status"].values():
            assert "status" in v
            assert v["status"] in _ALLOWED_STATUSES


# ---------------------------------------------------------------------------
# TestNotSupportedSemantics — known not_supported provider/tool pairings
# ---------------------------------------------------------------------------

class TestNotSupportedSemantics:
    """Verify that a known not_supported provider/tool pairing yields status == 'not_supported'.

    arXiv does not support citation data in V1.  The forward_citations and
    backward_references tools set arxiv -> not_supported unconditionally.
    We test the pure model/construction path here without any network calls.
    """

    def test_arxiv_not_supported_for_citations(self):
        """Constructing the citations output with arxiv=not_supported mirrors server behaviour."""
        work = _minimal_work()
        provider_status = {
            "openalex": ProviderStatus(status="not_supported"),
            "arxiv": ProviderStatus(
                status="not_supported",
                message="Not supported by this provider in V1",
            ),
        }
        out = CitationsOutput(
            work_key=work.work_key,
            results=[],
            markdown="",
            provider_status=provider_status,
        )
        assert out.provider_status["arxiv"].status == "not_supported"

    def test_not_supported_status_value_is_exact_string(self):
        ps = ProviderStatus(status="not_supported")
        assert ps.status == "not_supported"
        # Must not be confused with any other status string
        assert ps.status != "error"
        assert ps.status != "ok"

    def test_not_supported_round_trip_via_model_dump(self):
        """not_supported survives model_dump / re-instantiation."""
        ps = ProviderStatus(status="not_supported", message="Not supported")
        d = ps.model_dump()
        ps2 = ProviderStatus.model_validate(d)
        assert ps2.status == "not_supported"

    def test_get_work_output_provider_status_shape(self):
        """GetWorkOutput.provider_status also follows the mapping contract."""
        work = _minimal_work()
        ps_map = {
            "openalex": ProviderStatus(status="ok"),
            "arxiv": ProviderStatus(status="ok"),
        }
        out = GetWorkOutput(work=work, markdown="", provider_status=ps_map)
        for k, v in out.provider_status.items():
            assert isinstance(k, str)
            assert isinstance(v, ProviderStatus)
            assert v.status in _ALLOWED_STATUSES
