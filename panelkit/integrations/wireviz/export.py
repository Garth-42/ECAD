"""Export one harness to a WireViz YAML document.

One ``Harness`` maps to one WireViz document (the altitude principle: WireViz
documents the construction of a single harness, never the whole panel).
Pure projection — nothing here mutates the model.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ...model.connectivity import Wire, natural_key, wires_consistent
from ...model.harness import Bundle, Harness
from ...model.project import Project
from ...rules.checks import Finding
from .mapping import to_iec_color, to_wireviz_gauge


def _harness(project: Project, harness_id: str) -> Harness:
    harness = project.harnesses.get(harness_id)
    if harness is None:
        raise ValueError(
            f"unknown harness {harness_id!r} (known: {sorted(project.harnesses) or 'none'})"
        )
    return harness


def _wire_color(wire: Wire, warnings: list[Finding]) -> str:
    """Normalized IEC color; ``wire.wireviz_color`` takes precedence."""
    raw = wire.wireviz_color if wire.wireviz_color is not None else wire.color
    code, known = to_iec_color(raw)
    if not known:
        warnings.append(
            Finding(
                severity="warning",
                code="wireviz_color",
                message=f"wire {wire.number}: color {raw!r} is not a known IEC name; "
                "passing it through unchanged",
                refs=(wire.id,),
            )
        )
    return code


def _endpoint_pair(wires: list[Wire], designator: str) -> tuple[str, str]:
    """The (left, right) component pair of a point-to-point wire group."""
    pairs = {frozenset((w.source[0], w.target[0])) for w in wires}
    if len(pairs) != 1 or len(next(iter(pairs))) != 2:
        raise ValueError(
            f"cable {designator!r} is not point-to-point: endpoint pairs "
            f"{sorted(sorted(p) for p in pairs)} (v1 bundles must join exactly "
            "two components; model splits as multiple bundles)"
        )
    left, right = sorted(next(iter(pairs)))
    return left, right


def _require_connectors(wires: list[Wire], connectors: dict, harness_id: str) -> None:
    """Every wire end must land on a component the harness includes."""
    for wire in wires:
        for tag, _pin in (wire.source, wire.target):
            if tag not in connectors:
                raise ValueError(
                    f"harness {harness_id!r}: wire {wire.number} ends on {tag!r}, "
                    "which is not one of the harness's components"
                )


def _pin_on(wire: Wire, tag: str) -> str:
    return wire.source[1] if wire.source[0] == tag else wire.target[1]


def _pin_number(connectors: dict, tag: str, pin: str, wire: Wire) -> int:
    """1-based position of ``pin`` on connector ``tag``.

    Connections are written with pin *positions*, never labels: WireViz turns
    any numeric-looking label into an integer and reads it as a position, so
    a label such as ``"13"`` on a 10-pin contactor fails ("K1:13 not found")
    and ``"1"`` silently lands on whatever pin happens to be first. Positions
    are unambiguous; the labels still show in the drawing via ``pinlabels``.
    """
    labels = connectors[tag]["pinlabels"]
    try:
        return labels.index(pin) + 1
    except ValueError:
        raise ValueError(
            f"wire {wire.number}: pin {tag}:{pin} does not exist on part "
            f"{connectors[tag]['pn']!r}"
        ) from None


def _cable_length(wires: list[Wire], designator: str, warnings: list[Finding]) -> str | None:
    """Cable length = the longest routed member (mm); omitted when unrouted."""
    lengths = [w.length_mm for w in wires]
    if any(length is None for length in lengths):
        warnings.append(
            Finding(
                severity="warning",
                code="wireviz_length",
                message=f"cable {designator!r}: not all member wires are routed; "
                "omitting length (run the router first)",
                refs=(designator,),
            )
        )
        return None
    return f"{round(max(lengths), 1)} mm"


def _cable_entry(bundle: Bundle, wires: list[Wire], warnings: list[Finding]) -> dict:
    entry: dict = {"wirecount": len(wires), "wirelabels": [w.number for w in wires]}
    if bundle.kind == "bundle":
        entry["category"] = "bundle"
    gauges = sorted({to_wireviz_gauge(w.gauge) for w in wires})
    if len(gauges) == 1:
        entry["gauge"] = gauges[0]
    else:
        warnings.append(
            Finding(
                severity="warning",
                code="wireviz_gauge",
                message=f"cable {bundle.name!r}: mixed gauges {gauges}; omitting gauge",
                refs=(bundle.id,),
            )
        )
    if bundle.color_code is not None:
        entry["color_code"] = bundle.color_code
    else:
        entry["colors"] = [_wire_color(w, warnings) for w in wires]
    length = _cable_length(wires, bundle.name, warnings)
    if length is not None:
        entry["length"] = length
    for key, value in (
        ("pn", bundle.pn),
        ("manufacturer", bundle.manufacturer),
        ("mpn", bundle.mpn),
    ):
        if value is not None:
            entry[key] = value
    return entry


def to_wireviz_dict(project: Project, harness_id: str) -> tuple[dict, list[Finding]]:
    """Build the WireViz document for one harness as a plain dict."""
    harness = _harness(project, harness_id)
    warnings: list[Finding] = []
    if not wires_consistent(project):
        warnings.append(
            Finding(
                severity="warning",
                code="stale_wires",
                message="stored wires no longer match the nets; this harness may be out "
                "of date (re-resolve and re-route, then rebuild the harness)",
                refs=(harness.id,),
            )
        )

    connectors: dict = {}
    for tag in sorted(harness.component_tags):
        component = project.components.get(tag)
        if component is None:
            raise ValueError(f"harness {harness_id!r} references unknown component {tag!r}")
        part = project.part_of(component)
        connectors[tag] = {
            "type": part.description,
            "pinlabels": [pin.name for pin in part.pins],
            "pn": part.part_number,
            "manufacturer": part.manufacturer,
        }

    missing = sorted(w for w in harness.wire_ids if w not in project.wires)
    if missing:
        raise ValueError(f"harness {harness_id!r} references unknown wires: {missing}")

    bundled_wire_ids: set[str] = set()
    cables: dict = {}
    connections: list = []

    # Bundles first (sorted by cable name), each one connection set.
    missing_bundles = sorted(b for b in harness.bundle_ids if b not in project.bundles)
    if missing_bundles:
        raise ValueError(f"harness {harness_id!r} references unknown bundles: {missing_bundles}")
    for bundle in sorted((project.bundles[b] for b in harness.bundle_ids), key=lambda b: b.name):
        missing = sorted(w for w in bundle.wire_ids if w not in project.wires)
        if missing:
            raise ValueError(f"bundle {bundle.id!r} references unknown wires: {missing}")
        wires = sorted(
            (project.wires[w] for w in bundle.wire_ids), key=lambda w: natural_key(w.number)
        )
        _require_connectors(wires, connectors, harness_id)
        left, right = _endpoint_pair(wires, bundle.name)
        if bundle.name in cables:
            raise ValueError(f"duplicate cable designator {bundle.name!r}")
        cables[bundle.name] = _cable_entry(bundle, wires, warnings)
        connections.append(
            [
                {left: [_pin_number(connectors, left, _pin_on(w, left), w) for w in wires]},
                {bundle.name: list(range(1, len(wires) + 1))},
                {right: [_pin_number(connectors, right, _pin_on(w, right), w) for w in wires]},
            ]
        )
        bundled_wire_ids.update(w.id for w in wires)

    # Loose wires: one single-conductor cable each (v1), sorted by number.
    loose = sorted(
        (project.wires[w] for w in harness.wire_ids if w not in bundled_wire_ids),
        key=lambda w: natural_key(w.number),
    )
    _require_connectors(loose, connectors, harness_id)
    for wire in loose:
        if wire.source[0] == wire.target[0]:
            # A jumper between two pins of one component is not a cable: it is
            # a WireViz "loop" on that connector. Loops address pins by
            # position and carry no gauge/colour.
            tag = wire.source[0]
            connectors[tag].setdefault("loops", []).append(
                [
                    _pin_number(connectors, tag, wire.source[1], wire),
                    _pin_number(connectors, tag, wire.target[1], wire),
                ]
            )
            continue
        designator = f"W{wire.number}"
        if designator in cables:
            raise ValueError(
                f"cable designator collision: {designator!r} is already taken by a bundle"
            )
        entry: dict = {
            "category": "bundle",  # a loose wire BOMs as wire, not jacketed cable
            "wirecount": 1,
            "wirelabels": [wire.number],
            "gauge": to_wireviz_gauge(wire.gauge),
            "colors": [_wire_color(wire, warnings)],
        }
        length = _cable_length([wire], designator, warnings)
        if length is not None:
            entry["length"] = length
        cables[designator] = entry
        left, right = _endpoint_pair([wire], designator)
        connections.append(
            [
                {left: [_pin_number(connectors, left, _pin_on(wire, left), wire)]},
                {designator: [1]},
                {right: [_pin_number(connectors, right, _pin_on(wire, right), wire)]},
            ]
        )

    doc = {
        "metadata": {
            "title": harness.name,
            "pn": harness.id,
            "notes": f"Exported by PanelKit from project {project.name!r}; "
            "cable lengths are routed lengths in millimetres.",
        },
        "connectors": connectors,
        "cables": cables,
        "connections": connections,
    }
    return doc, warnings


def to_yaml(project: Project, harness_id: str) -> tuple[str, list[Finding]]:
    """The harness as deterministic YAML (sorted keys, fixed style)."""
    doc, warnings = to_wireviz_dict(project, harness_id)
    text = yaml.safe_dump(doc, sort_keys=True, default_flow_style=False, allow_unicode=True)
    return text, warnings


def export(project: Project, harness_id: str, path: str | Path) -> list[Finding]:
    """Write the harness YAML to ``path``; returns any normalization warnings."""
    text, warnings = to_yaml(project, harness_id)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return warnings
