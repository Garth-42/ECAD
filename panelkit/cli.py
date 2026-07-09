"""PanelKit command-line interface (argparse)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .examples.motor_start_stop import build_project_with_harness
from .integrations.wireviz.export import export as export_wireviz_yaml
from .integrations.wireviz.runner import WirevizNotFoundError, render, wireviz_available
from .library.parts import PartLibrary
from .model.project import Project
from .persistence import load_project, save_project
from .routing.resolve import resolve_wires
from .routing.router import render_cut_list, route_wires
from .rules.checks import validate
from .views.bom import render_bom
from .views.connection_list import render_connection_list
from .views.netlist import render_netlist
from .views.svg_schematic import render_schematic
from .views.svg_wiring import render_wiring
from .views.terminal_plan import render_terminal_plan


def _library(args: argparse.Namespace) -> PartLibrary:
    lib = PartLibrary.bundled()
    if args.library:
        lib.load_directory(Path(args.library))
    return lib


def _load(args: argparse.Namespace) -> Project:
    return load_project(args.project, _library(args))


def cmd_validate(args: argparse.Namespace) -> int:
    findings = validate(_load(args))
    for f in findings:
        refs = f" [{', '.join(f.refs)}]" if f.refs else ""
        print(f"{f.severity.upper():<8} {f.code:<18} {f.message}{refs}")
    errors = [f for f in findings if f.severity == "error"]
    print(f"{len(findings)} finding(s), {len(errors)} error(s)")
    return 1 if errors else 0


def cmd_bom(args: argparse.Namespace) -> int:
    print(render_bom(_load(args)), end="")
    return 0


def cmd_netlist(args: argparse.Namespace) -> int:
    print(render_netlist(_load(args)), end="")
    return 0


def cmd_connections(args: argparse.Namespace) -> int:
    print(render_connection_list(_load(args)), end="")
    return 0


def cmd_terminals(args: argparse.Namespace) -> int:
    print(render_terminal_plan(_load(args)), end="")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    project = _load(args)
    resolve_wires(project)
    route_wires(project)
    print(render_cut_list(project), end="")
    return 0


def _render(args: argparse.Namespace, renderer) -> int:
    project = _load(args)
    if not project.wires:
        resolve_wires(project)
        route_wires(project)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(renderer(project))
    print(f"wrote {out}")
    return 0


def cmd_render_schematic(args: argparse.Namespace) -> int:
    return _render(args, render_schematic)


def cmd_render_wiring(args: argparse.Namespace) -> int:
    return _render(args, render_wiring)


def cmd_harness_list(args: argparse.Namespace) -> int:
    project = _load(args)
    if not project.harnesses:
        print("no harnesses defined")
        return 0
    print(f"{'ID':<8} {'NAME':<20} {'COMPONENTS':>10} {'WIRES':>6} {'BUNDLES':>8}")
    for hid in sorted(project.harnesses):
        h = project.harnesses[hid]
        print(
            f"{h.id:<8} {h.name:<20} {len(h.component_tags):>10} "
            f"{len(h.wire_ids):>6} {len(h.bundle_ids):>8}"
        )
    return 0


def _print_warnings(warnings) -> None:
    for f in warnings:
        print(f"{f.severity.upper():<8} {f.code:<16} {f.message}")


def cmd_export_wireviz(args: argparse.Namespace) -> int:
    project = _load(args)
    if args.render:
        out_dir = Path(args.output)
        yaml_path = out_dir / f"{args.harness}.yml"
    else:
        yaml_path = Path(args.output)
    _print_warnings(export_wireviz_yaml(project, args.harness, yaml_path))
    print(f"wrote {yaml_path}")
    if not args.render:
        return 0
    try:
        for produced in render(yaml_path, yaml_path.parent):
            print(f"wrote {produced}")
    except WirevizNotFoundError as exc:
        # The YAML stays where it was written; only the render step failed.
        print(f"error: {exc}")
        return 1
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    project = build_project_with_harness()
    save_project(project, out_dir / "project.json")
    (out_dir / "schematic.svg").write_text(render_schematic(project))
    (out_dir / "wiring.svg").write_text(render_wiring(project))
    print(f"wrote {out_dir / 'project.json'}")
    print(f"wrote {out_dir / 'schematic.svg'}")
    print(f"wrote {out_dir / 'wiring.svg'}")
    for harness_id in sorted(project.harnesses):
        yaml_path = out_dir / f"{harness_id}.yml"
        _print_warnings(export_wireviz_yaml(project, harness_id, yaml_path))
        print(f"wrote {yaml_path}")
        if wireviz_available():
            for produced in render(yaml_path, out_dir):
                print(f"wrote {produced}")
        else:
            print(f"note: 'wireviz' not on PATH; skipped rendering {yaml_path.name}")
    findings = validate(project)
    errors = [f for f in findings if f.severity == "error"]
    print(f"validate: {len(findings)} finding(s), {len(errors)} error(s)")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="panelkit",
        description="Electrical panel design toolkit — one model, many views.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_: str, project_arg: bool = True, output: str | None = None):
        p = sub.add_parser(name, help=help_)
        if project_arg:
            p.add_argument("project", help="project file (.json, or .db/.sqlite for SQLite)")
            p.add_argument("--library", help="extra parts directory", default=None)
        p.set_defaults(func=func)
        if output:
            p.add_argument("-o", "--output", required=True, help=output)
        return p

    add("validate", cmd_validate, "run all checks; exit 1 on any error")
    add("bom", cmd_bom, "print the bill of materials")
    add("netlist", cmd_netlist, "print the netlist")
    add("connections", cmd_connections, "print the connection list")
    add("terminals", cmd_terminals, "print the terminal plan")
    add("route", cmd_route, "resolve + route; print the cut list")
    add("render-schematic", cmd_render_schematic, "write the schematic SVG", output="output .svg")
    add("render-wiring", cmd_render_wiring, "write the wiring diagram SVG", output="output .svg")

    harness = sub.add_parser("harness", help="harness inspection commands")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    hlist = harness_sub.add_parser("list", help="list harnesses with counts")
    hlist.add_argument("project", help="project file (.json, or .db/.sqlite for SQLite)")
    hlist.add_argument("--library", help="extra parts directory", default=None)
    hlist.set_defaults(func=cmd_harness_list)

    wv = add(
        "export-wireviz",
        cmd_export_wireviz,
        "export one harness to WireViz YAML",
        output="output .yml (or a directory with --render)",
    )
    wv.add_argument("--harness", required=True, help="harness id to export")
    wv.add_argument(
        "--render",
        action="store_true",
        help="also run the wireviz CLI; -o names the output directory",
    )
    add(
        "demo",
        cmd_demo,
        "build the example; write JSON + both SVGs",
        project_arg=False,
        output="output directory",
    )

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
