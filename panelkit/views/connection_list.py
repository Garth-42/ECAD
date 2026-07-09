"""Connection list view: every resolved wire, endpoint to endpoint."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.connectivity import Wire
from ..model.project import Project
from ..routing.resolve import compute_wires


@dataclass(frozen=True)
class ConnectionRow:
    number: str
    source: str  # "TAG:PIN"
    target: str
    net_name: str
    gauge: str
    color: str


def _wires(project: Project) -> list[Wire]:
    """Resolved wires — from the model when present, else computed locally."""
    wires = project.wires or compute_wires(project)
    return [wires[k] for k in sorted(wires)]


def connection_list(project: Project) -> list[ConnectionRow]:
    rows = []
    for w in _wires(project):
        net = project.nets.get(w.net_id)
        rows.append(
            ConnectionRow(
                number=w.number,
                source=f"{w.source[0]}:{w.source[1]}",
                target=f"{w.target[0]}:{w.target[1]}",
                net_name=net.name if net else "?",
                gauge=w.gauge,
                color=w.color,
            )
        )
    return sorted(rows, key=lambda r: r.number)


def render_connection_list(project: Project) -> str:
    lines = [
        f"CONNECTIONS — {project.name}",
        "",
        f"{'WIRE':<6} {'FROM':<10} {'TO':<10} {'NET':<10} {'GAUGE':<10} COLOR",
    ]
    for r in connection_list(project):
        lines.append(
            f"{r.number:<6} {r.source:<10} {r.target:<10} {r.net_name:<10} {r.gauge:<10} {r.color}"
        )
    return "\n".join(lines) + "\n"
