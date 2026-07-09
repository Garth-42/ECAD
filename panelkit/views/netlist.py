"""Netlist view: every net with its member pins."""

from __future__ import annotations

from ..model.component import PinRef
from ..model.project import Project

NetRow = tuple[str, str, list[PinRef]]  # (net_id, name, sorted pins)


def netlist(project: Project) -> list[NetRow]:
    return [(net.id, net.name, sorted(net.pins)) for net in project.iter_nets()]


def render_netlist(project: Project) -> str:
    lines = [f"NETLIST — {project.name}", ""]
    for net_id, name, pins in netlist(project):
        joined = ", ".join(f"{tag}:{pin}" for tag, pin in pins)
        lines.append(f"{net_id:<8} {name:<10} {joined}")
    return "\n".join(lines) + "\n"
