"""Minimal SVG element builders — plain strings, no dependencies."""

from __future__ import annotations

from xml.sax.saxutils import escape


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _attrs(attrs: dict[str, object]) -> str:
    parts = []
    for key in sorted(attrs):
        value = attrs[key]
        if value is None:
            continue
        name = key.rstrip("_").replace("_", "-")
        parts.append(f'{name}="{escape(_fmt(value))}"')
    return (" " + " ".join(parts)) if parts else ""


def rect(x: float, y: float, w: float, h: float, **attrs: object) -> str:
    return (
        f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}"{_attrs(attrs)} />'
    )


def line(x1: float, y1: float, x2: float, y2: float, **attrs: object) -> str:
    return (
        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}"{_attrs(attrs)} />'
    )


def circle(cx: float, cy: float, r: float, **attrs: object) -> str:
    return f'<circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(r)}"{_attrs(attrs)} />'


def polyline(points: list[tuple[float, float]], **attrs: object) -> str:
    pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    return f'<polyline points="{pts}" fill="none"{_attrs(attrs)} />'


def text(x: float, y: float, content: str, **attrs: object) -> str:
    return f'<text x="{_fmt(x)}" y="{_fmt(y)}"{_attrs(attrs)}>{escape(content)}</text>'


def group(children: list[str], **attrs: object) -> str:
    inner = "\n".join(children)
    return f"<g{_attrs(attrs)}>\n{inner}\n</g>"


class Canvas:
    """Accumulates SVG elements; serializes to a standalone SVG document."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self._elements: list[str] = []

    def add(self, element: str) -> None:
        self._elements.append(element)

    def to_svg(self) -> str:
        body = "\n".join(self._elements)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{_fmt(self.width)}" height="{_fmt(self.height)}" '
            f'viewBox="0 0 {_fmt(self.width)} {_fmt(self.height)}" '
            f'font-family="monospace">\n{body}\n</svg>\n'
        )
