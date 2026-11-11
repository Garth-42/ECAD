# PanelKit

A lightweight electrical-panel design toolkit: a Python library and CLI for
low-voltage control panels.

**The idea (borrowed from professional ECAD tools): model the connectivity,
not the drawing.** You describe components, how their pins connect (nets), and
where components sit on the backplate (placements) — once, in one project
model. Schematics, wiring diagrams, bills of material, terminal plans, and
wire cut lists are all *views* derived from that single source of truth, so
they can never disagree with each other.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # runtime deps + pytest/ruff/black
```

Requires Python 3.11+. Runtime dependencies: `numpy`, `networkx`, `scipy`,
`pyyaml`.

## Smoke test

```bash
panelkit demo -o out/
```

This builds the bundled motor start/stop example, validates it, and writes
`out/project.json`, `out/schematic.svg`, and `out/wiring.svg` (open the SVGs
in any browser).

## Commands

Every command takes a project file path (see `out/project.json` for the
format). Files ending in `.db`, `.sqlite`, or `.sqlite3` use the equivalent
SQLite backend; anything else is treated as JSON. Add `--library <dir>` to any
command to load extra part definitions (they override bundled parts with the
same part number).

```bash
panelkit validate <project.json|.db>        # run checks; exit 1 on any error
panelkit bom <project.json>                 # bill of materials
panelkit netlist <project.json>             # nets and their pins
panelkit connections <project.json>         # resolved point-to-point wires
panelkit terminals <project.json>           # terminal-strip plan
panelkit route <project.json>               # duct-routed wire lengths (cut list)
panelkit render-schematic <project.json> -o schematic.svg
panelkit render-wiring <project.json> -o wiring.svg
panelkit harness list <project.json>        # harnesses with component/wire counts
panelkit export-wireviz <project.json> --harness H1 -o H1.yml
panelkit export-wireviz <project.json> --harness H1 --render -o out/
```

Exit codes: `0` success, `1` the project has validation errors (or a WireViz
render failed), `2` the command could not run (missing or corrupt file, unknown
harness, ...) — reported as a one-line `error:` message on stderr.

**Wires are derived from nets.** A saved project may contain resolved wires,
but the nets stay the source of truth: if you edit the nets in a project file,
the text and SVG views recompute the wires rather than show stale ones, and
`validate` reports `stale_wires` so you know stored lengths, bundles, and
harnesses need rebuilding.

## WireViz harness export

A **harness** is a named, build-level subset of the panel (components +
wires/bundles); each harness exports to one
[WireViz](https://github.com/wireviz/WireViz) YAML document with connectors,
cables/bundles, IEC colors, gauges, and routed lengths. `--render` shells out
to an installed `wireviz` CLI (optional — install with
`pip install "panelkit[wireviz]"`, rendering also needs GraphViz) to produce
the harness drawing and BOM. PanelKit itself never imports WireViz; the
integration is a generated file plus a subprocess.

Connections are exported by pin *position* (WireViz would misread numeric pin
labels such as `13`), a jumper between two pins of one component becomes a
WireViz connector `loop`, and two-colour wires such as `green/yellow` map to
the combined IEC code (`GNYE`).

## How it fits together

- **Model** (`panelkit/model/`) — components (instances of library parts),
  nets, wires, placements (mm, rotations restricted to 0/90/180/270°),
  mounting surfaces, and wire ducts.
- **Library** (`panelkit/library/`) — part definitions (pins, geometry,
  ratings) loaded from JSON; bundled parts live in `library/data/`.
- **Rules** (`panelkit/rules/`) — pure checks: duplicate tags, unknown parts,
  unconnected pins, net pins that reference a missing component or pin, pins
  listed in more than one net, stale wires, degenerate ducts, empty nets,
  overcurrent, invalid rotation, and clearance (per mounting surface).
- **Routing** (`panelkit/routing/`) — nets resolve to discrete two-point wires
  (star topology through terminal blocks, otherwise a nearest-neighbour daisy
  chain), then route through the duct network for real lengths. Ducts join
  wherever they touch or cross. With no ducts wires are straight lines; a wire
  whose ends sit on disconnected duct sections also falls back to a straight
  line, and `panelkit route` warns about it.
- **Views** (`panelkit/views/`) — read-only projections: text reports plus two
  SVG renderers (ladder-style schematic and geometric backplate diagram).
  Views never mutate the model.

## Development

```bash
pytest             # full test suite
ruff check .       # lint
black .            # format
```
