"""Intel feature-flag scaffold — internal use only.

Env var: SCHOLARLY_GATEWAY_INTEL_ENABLED
Truthy values: "1", "true", "yes", "on" (case-insensitive).
Default: disabled (no side effects, no output changes).

Env var: SCHOLARLY_GATEWAY_INTEL_DB_PATH
Default: ./.data/scholarly_gateway_intel.db (created only when enabled).
"""
from __future__ import annotations

import os
from typing import Any, Optional


def intel_enabled() -> bool:
    """Return True only when the intel feature flag is explicitly enabled."""
    val = os.environ.get("SCHOLARLY_GATEWAY_INTEL_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _intel_db_path() -> str:
    return os.environ.get(
        "SCHOLARLY_GATEWAY_INTEL_DB_PATH",
        "./.data/scholarly_gateway_intel.db",
    )


class IntelSink:
    """Thin sink that delegates writes to IntelLedger. Fail-open."""

    def __init__(self) -> None:
        from scholarly_gateway.intel_ledger import IntelLedger
        self._ledger = IntelLedger(_intel_db_path())

    def record_event(self, event_type: str, payload: Any, **kwargs: Any) -> None:
        try:
            self._ledger.append_event(event_type, payload, **kwargs)
        except Exception:  # noqa: BLE001
            pass


def get_intel_sink() -> Optional[IntelSink]:
    """Return an IntelSink when enabled, None otherwise.

    Fail-open: any exception during init returns None silently.
    """
    if not intel_enabled():
        return None
    try:
        return IntelSink()
    except Exception:  # noqa: BLE001
        return None
