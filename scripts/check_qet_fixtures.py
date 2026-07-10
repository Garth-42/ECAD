#!/usr/bin/env python3
"""Verify the QET import fixtures agree with each other, and probe real QET files.

Two modes:

  check (default)
      Re-derive the golden import result from ``motor_start_stop.qet`` +
      ``motor_start_stop.terminal_map.json`` by the documented rules
      (tests/data/README.md) and diff it against
      ``motor_start_stop.import.golden.json``. Run after touching any fixture.

  --probe [PATH ...]
      Parse real QET project files (default: the genuine QET-authored examples
      shipped by the ``qelectrotech`` package under
      /usr/share/qelectrotech/examples) and report the schema facts the
      importer relies on: terminal-name emptiness, per-folio terminal-id
      uniqueness, conductor num usage, embed:// type paths. A drift here means
      the importer's assumptions need revisiting.

Stdlib only (xml.etree + json) so it runs anywhere, including CI, without
PanelKit installed.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "tests" / "data"
QET_EXAMPLES = Path("/usr/share/qelectrotech/examples")

UNNAMED = {None, "", "_"}  # verified: real terminal names are absent, "", or "_"


def _connected_components(edges: list[tuple[int, int]]) -> list[set[int]]:
    adjacency: dict[int, set[int]] = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    seen: set[int] = set()
    components = []
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency[node] - component)
        seen |= component
        components.append(component)
    return components


def derive_import(qet_path: Path, terminal_map_path: Path) -> dict:
    """Apply the documented import rules; returns golden-shaped dict."""
    terminal_map = {
        k: v for k, v in json.loads(terminal_map_path.read_text()).items() if k != "_comment"
    }
    root = ET.parse(qet_path).getroot()
    diagrams = [d for d in root.findall("diagram") if d.find(".//element") is not None]
    if len(diagrams) != 1:
        raise SystemExit(f"v1 scope is single-folio: found {len(diagrams)} diagrams with elements")
    diagram = diagrams[0]

    term_pin: dict[int, tuple[str, str]] = {}
    components: dict[str, dict] = {}
    for element in diagram.findall("./elements/element"):
        basename = element.get("type", "").rsplit("/", 1)[-1]
        pins = terminal_map.get(basename)
        if pins is None:
            raise SystemExit(f"element type {basename!r} missing from terminal map")
        infos = {i.get("name"): (i.text or "") for i in element.iter("elementInformation")}
        tag = infos.get("label", "")
        part = infos.get("manufacturer_reference") or infos.get("panelkit_pn", "")
        if not tag or not part:
            raise SystemExit(f"element {basename!r}: missing label or part-number info field")
        terminals = element.findall("./terminals/terminal")
        if len(terminals) != len(pins):
            raise SystemExit(f"{tag}: {len(terminals)} terminals vs {len(pins)} mapped pins")
        for i, t in enumerate(terminals):
            if t.get("name") not in UNNAMED:
                raise SystemExit(f"{tag}: unexpected meaningful terminal name {t.get('name')!r}")
            term_pin[int(t.get("id"))] = (tag, pins[i])
        components[tag] = {"part_number": part, "placement": None, "surface_id": None}

    edges = []
    for c in diagram.findall("./conductors/conductor"):
        edges.append((int(c.get("terminal1")), int(c.get("terminal2"))))
    nets: dict[str, dict] = {}
    ordered = sorted(_connected_components(edges), key=min)  # NUMERIC min-id order
    for i, terminal_ids in enumerate(ordered, 1):
        # (conductor-num naming not exercised by this fixture: all num="")
        name = f"NET_{i:04d}"
        pins_sorted = sorted([list(term_pin[t]) for t in terminal_ids])  # string sort
        nets[name] = {"name": name, "pins": pins_sorted, "properties": {}}

    return {
        "bundles": {},
        "components": dict(sorted(components.items())),
        "ducts": {},
        "format_version": 2,
        "harnesses": {},
        "name": root.get("title", ""),
        "nets": nets,
        "surfaces": {},
        "wires": {},
    }


def cmd_check() -> int:
    derived = derive_import(
        DATA / "motor_start_stop.qet", DATA / "motor_start_stop.terminal_map.json"
    )
    golden = json.loads((DATA / "motor_start_stop.import.golden.json").read_text())
    if derived == golden:
        print(
            f"OK: fixtures consistent — {len(golden['components'])} components, "
            f"{len(golden['nets'])} nets re-derived exactly"
        )
        return 0
    for key in sorted(set(derived) | set(golden)):
        if derived.get(key) != golden.get(key):
            print(f"MISMATCH in {key!r}:")
            if isinstance(golden.get(key), dict):
                for sub in sorted(set(derived.get(key, {})) | set(golden.get(key, {}))):
                    d, g = derived.get(key, {}).get(sub), golden.get(key, {}).get(sub)
                    if d != g:
                        print(f"  {sub}: derived={d}\n  {' ' * len(sub)}  golden ={g}")
            else:
                print(f"  derived={derived.get(key)}\n  golden ={golden.get(key)}")
    return 1


def cmd_probe(paths: list[Path]) -> int:
    failures = 0
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(f"{path.name}: XML PARSE ERROR: {exc}")
            failures += 1
            continue
        diagrams = root.findall("diagram")
        bad_names = Counter()
        embed_types = plain_types = 0
        per_folio_dupes = 0
        num_filled = num_empty = 0
        for d in diagrams:
            ids = []
            for e in d.findall(".//elements/element"):
                if (e.get("type") or "").startswith("embed://"):
                    embed_types += 1
                else:
                    plain_types += 1
                for t in e.findall("./terminals/terminal"):
                    ids.append(t.get("id"))
                    if t.get("name") not in UNNAMED:
                        bad_names[t.get("name")] += 1
            per_folio_dupes += sum(1 for _, n in Counter(ids).items() if n > 1)
            for c in d.findall(".//conductors/conductor"):
                if (c.get("num") or "") == "":
                    num_empty += 1
                else:
                    num_filled += 1
        print(
            f"{path.name}: format={root.get('version')} folios={len(diagrams)} "
            f"types embed/plain={embed_types}/{plain_types} "
            f"per-folio id dupes={per_folio_dupes} "
            f"num filled/empty={num_filled}/{num_empty} "
            f"meaningful terminal names={sum(bad_names.values())}"
        )
        if bad_names:
            print(f"  DRIFT: terminal names no longer placeholders: {bad_names.most_common(5)}")
            failures += 1
        if per_folio_dupes:
            print("  DRIFT: terminal ids not unique within a folio")
            failures += 1
    print("PROBE:", "DRIFT DETECTED" if failures else "all assumptions hold")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", nargs="*", metavar="QET_FILE", default=None)
    args = parser.parse_args()
    if args.probe is None:
        return cmd_check()
    paths = [Path(p) for p in args.probe] or sorted(QET_EXAMPLES.glob("*.qet"))
    if not paths:
        print(f"no .qet files found (looked in {QET_EXAMPLES}); install 'qelectrotech'")
        return 1
    return cmd_probe(paths)


if __name__ == "__main__":
    sys.exit(main())
