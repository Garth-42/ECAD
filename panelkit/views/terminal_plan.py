"""Terminal plan view: what lands on each terminal-block point."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.project import Project
from .connection_list import _wires


@dataclass(frozen=True)
class TerminalRow:
    terminal: str  # terminal block tag
    point: str  # pin name on the strip
    net_name: str
    connected: tuple[str, ...]  # far ends, "TAG:PIN"


def terminal_plan(project: Project) -> list[TerminalRow]:
    wires = _wires(project)
    rows = []
    for c in project.iter_components():
        if project.part_of(c).category != "terminal_block":
            continue
        for pin_def in project.part_of(c).pins:
            ref = (c.tag, pin_def.name)
            far = sorted(
                w.source if w.target == ref else w.target
                for w in wires
                if ref in (w.source, w.target)
            )
            net = project.net_of(ref)
            rows.append(
                TerminalRow(
                    terminal=c.tag,
                    point=pin_def.name,
                    net_name=net.name if net else "-",
                    connected=tuple(f"{t}:{p}" for t, p in far),
                )
            )
    return rows


def render_terminal_plan(project: Project) -> str:
    lines = [f"TERMINAL PLAN — {project.name}", ""]
    current = None
    for r in terminal_plan(project):
        if r.terminal != current:
            current = r.terminal
            lines.append(f"[{r.terminal}]")
            lines.append(f"  {'POINT':<6} {'NET':<10} CONNECTED")
        lines.append(f"  {r.point:<6} {r.net_name:<10} {', '.join(r.connected) or '-'}")
    return "\n".join(lines) + "\n"
