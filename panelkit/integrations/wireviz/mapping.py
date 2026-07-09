"""Normalization helpers for the WireViz export: colors and gauges."""

from __future__ import annotations

# IEC 60757 two-character color abbreviations, keyed by common color names.
IEC_COLORS: dict[str, str] = {
    "black": "BK",
    "red": "RD",
    "green": "GN",
    "yellow": "YE",
    "blue": "BU",
    "white": "WH",
    "brown": "BN",
    "orange": "OG",
    "grey": "GY",
    "gray": "GY",
    "violet": "VT",
    "purple": "VT",
    "pink": "PK",
    "turquoise": "TQ",
}

_IEC_CODES = frozenset(IEC_COLORS.values())


def to_iec_color(value: str) -> tuple[str, bool]:
    """Normalize a color name to an IEC code.

    Returns ``(code, known)``. Unknown values pass through unchanged with
    ``known=False`` so the exporter can warn rather than crash.
    """
    if value.upper() in _IEC_CODES:
        return value.upper(), True
    code = IEC_COLORS.get(value.strip().lower())
    if code is not None:
        return code, True
    return value, False


def to_wireviz_gauge(value: str) -> str:
    """Pass mm2 / AWG gauge strings through in WireViz's accepted form.

    No mm2<->AWG conversion in v1 — only whitespace tidying.
    """
    return " ".join(value.split())
