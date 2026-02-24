"""Naming helpers for Protein Tracker entities and devices."""

from __future__ import annotations


SENSOR_SUFFIX = "Protein Tracker"
GOAL_SUFFIX = "Protein Ziel"


def _normalize_base_name(base_name: str) -> str:
    base = " ".join(str(base_name).split())
    if not base:
        return ""

    lowered = base.casefold()
    for marker in ("protein tracker", "protein ziel", "protein goal"):
        idx = lowered.find(marker)
        if idx == -1:
            continue
        base = f"{base[:idx]}{base[idx + len(marker):]}".strip()
        base = " ".join(base.split())
        lowered = base.casefold()

    return base


def _with_suffix(base_name: str, suffix: str) -> str:
    base = _normalize_base_name(base_name)
    if not base:
        return suffix
    if base.casefold().endswith(suffix.casefold()):
        return base
    return f"{base} {suffix}"


def base_display_name(base_name: str) -> str:
    """Return normalized base name without tracker/goal suffix fragments."""
    base = _normalize_base_name(base_name)
    return base or SENSOR_SUFFIX


def tracker_display_name(base_name: str) -> str:
    """Return sensor/device display name."""
    return _with_suffix(base_name, SENSOR_SUFFIX)


def goal_display_name(base_name: str) -> str:
    """Return goal-entity display name."""
    return _with_suffix(base_name, GOAL_SUFFIX)
