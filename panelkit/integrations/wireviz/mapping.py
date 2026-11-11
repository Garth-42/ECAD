"""Normalization helpers for the WireViz export: colors and gauges."""

from __future__ import annotations

from ...model.colors import IEC_COLORS, to_iec_color

__all__ = ["IEC_COLORS", "to_iec_color", "to_wireviz_gauge"]


def to_wireviz_gauge(value: str) -> str:
    """Pass mm2 / AWG gauge strings through in WireViz's accepted form.

    No mm2<->AWG conversion in v1 — only whitespace tidying.
    """
    return " ".join(value.split())
