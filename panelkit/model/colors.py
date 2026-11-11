"""Wire colour names: IEC 60757 codes and CSS equivalents.

Wire colours are stored as free text (``"red"``, ``"BU"``, ``"green/yellow"``).
These helpers normalize that text for the two places it is consumed: the
WireViz export (IEC codes) and the SVG views (CSS colour names).
"""

from __future__ import annotations

import re

# IEC 60757 two-character colour abbreviations, keyed by common colour names.
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

# First name listed for each code wins ("grey" before "gray", "violet" before
# "purple"); every value is a valid CSS colour keyword.
_CSS_BY_CODE: dict[str, str] = {}
for _name, _code in IEC_COLORS.items():
    _CSS_BY_CODE.setdefault(_code, _name)

# Multi-colour wires are written "green/yellow" (also "green-yellow").
_SEPARATORS = re.compile(r"[/\-]")


def _single_code(value: str) -> str | None:
    """IEC code for one colour given as a name or a code; None if unknown."""
    token = value.strip()
    if token.upper() in _IEC_CODES:
        return token.upper()
    return IEC_COLORS.get(token.lower())


def _codes(value: str) -> list[str] | None:
    """IEC codes for a (possibly multi-colour) value; None if any part is unknown."""
    token = value.strip()
    parts = [p for p in _SEPARATORS.split(token) if p.strip()]
    codes = [_single_code(p) for p in parts]
    if codes and all(c is not None for c in codes):
        return codes  # type: ignore[return-value]
    # Already-concatenated codes such as "GNYE".
    upper = token.upper()
    if upper and len(upper) % 2 == 0:
        pairs = [upper[i : i + 2] for i in range(0, len(upper), 2)]
        if all(p in _IEC_CODES for p in pairs):
            return pairs
    return None


def to_iec_color(value: str) -> tuple[str, bool]:
    """Normalize a colour name to an IEC code.

    Multi-colour wires concatenate their codes, the form WireViz expects:
    ``"green/yellow"`` -> ``"GNYE"``. Returns ``(code, known)``. Unknown values
    pass through unchanged with ``known=False`` so the exporter can warn
    rather than crash.
    """
    codes = _codes(value)
    if codes is None:
        return value, False
    return "".join(codes), True


def css_colors(value: str) -> list[str]:
    """CSS colour keywords for a wire colour, one per stripe.

    ``"green/yellow"`` -> ``["green", "yellow"]``; ``"BU"`` -> ``["blue"]``.
    Unknown values pass through as a single entry so custom CSS colours
    (``"#ff8800"``) keep working.
    """
    codes = _codes(value)
    if codes is None:
        return [value.strip()]
    return [_CSS_BY_CODE[c] for c in codes]
