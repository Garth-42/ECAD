"""Export one harness to a WireViz YAML document.

One ``Harness`` maps to one WireViz document (the altitude principle: WireViz
documents the construction of a single harness, never the whole panel).
Pure projection — nothing here mutates the model.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ...model.connectivity import Wire
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


def _pin_on(wire: Wire, tag: str) -> str:
    return wire.source[1] if wire.source[0] == tag else wire.target[1]


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
    for bundle in sorted((project.bundles[b] for b in harness.bundle_ids), key=lambda b: b.name):
        wires = sorted((project.wires[w] for w in bundle.wire_ids), key=lambda w: w.number)
        left, right = _endpoint_pair(wires, bundle.name)
        if bundle.name in cables:
            raise ValueError(f"duplicate cable designator {bundle.name!r}")
        cables[bundle.name] = _cable_entry(bundle, wires, warnings)
        connections.append(
            [
                {left: [_pin_on(w, left) for w in wires]},
                {bundle.name: list(range(1, len(wires) + 1))},
                {right: [_pin_on(w, right) for w in wires]},
            ]
        )
        bundled_wire_ids.update(w.id for w in wires)

    # Loose wires: one single-conductor cable each (v1), sorted by number.
    loose = sorted(
        (project.wires[w] for w in harness.wire_ids if w not in bundled_wire_ids),
        key=lambda w: w.number,
    )
    for wire in loose:
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
                {left: [_pin_on(wire, left)]},
                {designator: [1]},
                {right: [_pin_on(wire, right)]},
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
    out.write_text(text)
    return warnings
