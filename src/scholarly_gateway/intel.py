"""Intel feature-flag scaffold — internal use only.

Env var: SCHOLARLY_GATEWAY_INTEL_ENABLED
Truthy values: "1", "true", "yes", "on" (case-insensitive).
Default: disabled (no side effects, no output changes).
"""
from __future__ import annotations

import os
from typing import Optional


def intel_enabled() -> bool:
    """Return True only when the intel feature flag is explicitly enabled."""
    val = os.environ.get("SCHOLARLY_GATEWAY_INTEL_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


class IntelSink:
    """Placeholder sink — all methods are no-ops until the intelligence layer is built."""

    def record_event(self, *args: object, **kwargs: object) -> None:  # noqa: ANN401
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
