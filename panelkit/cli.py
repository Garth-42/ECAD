"""PanelKit command-line interface (argparse)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .examples.motor_start_stop import build_project
from .library.parts import PartLibrary
from .model.project import Project
from .persistence.json_store import load, save
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
    return load(args.project, _library(args))


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


def cmd_demo(args: argparse.Namespace) -> int:
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    project = build_project()
    resolve_wires(project)
    route_wires(project)
    save(project, out_dir / "project.json")
    (out_dir / "schematic.svg").write_text(render_schematic(project))
    (out_dir / "wiring.svg").write_text(render_wiring(project))
    print(f"wrote {out_dir / 'project.json'}")
    print(f"wrote {out_dir / 'schematic.svg'}")
    print(f"wrote {out_dir / 'wiring.svg'}")
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
            p.add_argument("project", help="path to project JSON")
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
