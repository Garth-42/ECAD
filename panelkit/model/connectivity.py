"""Connectivity: nets, wires, and the pin-adjacency graph."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING

import networkx as nx

from .component import PinRef

if TYPE_CHECKING:
    from .project import Project


@dataclass
class Net:
    id: str
    name: str
    pins: set[PinRef] = field(default_factory=set)
    properties: dict = field(default_factory=dict)


@dataclass
class Wire:
    id: str
    net_id: str
    source: PinRef
    target: PinRef
    number: str
    gauge: str = "1.0 mm2"
    color: str = "black"
    length_mm: float | None = None
    path: list[tuple[float, float, float]] | None = None
    wireviz_color: str | None = None  # explicit IEC 60757 code override (M9)


_DIGITS = re.compile(r"(\d+)")


def natural_key(text: str) -> tuple:
    """Sort key that orders embedded numbers numerically.

    Plain string sorting puts ``"1000"`` before ``"101"``; wire numbers and
    wire ids (``"w101"``) need numeric order. ``re.split`` with a capture
    group always alternates text, digits, text, ... so the mixed str/int
    tuples stay comparable position by position.
    """
    parts = _DIGITS.split(text)
    return tuple(int(p) if i % 2 else p for i, p in enumerate(parts))


def wires_consistent(project: Project) -> bool:
    """True when ``project.wires`` still realizes ``project.nets``.

    Wires are derived data: once nets are edited (e.g. by hand in a saved
    project file) stored wires can go stale. They are consistent when every
    wire joins two pins of its own net and every multi-pin net is fully
    connected by its wires. A project with no wires is trivially consistent.
    """
    if not project.wires:
        return True
    by_net: dict[str, list[Wire]] = {}
    for wire in project.wires.values():
        by_net.setdefault(wire.net_id, []).append(wire)
    if any(net_id not in project.nets for net_id in by_net):
        return False
    for net in project.nets.values():
        wires = by_net.get(net.id, [])
        g = nx.Graph()
        g.add_nodes_from(net.pins)
        for wire in wires:
            if wire.source not in net.pins or wire.target not in net.pins:
                return False
            g.add_edge(wire.source, wire.target)
        if len(net.pins) >= 2 and not nx.is_connected(g):
            return False
    return True


def build_graph(project: Project) -> nx.Graph:
    """Graph whose nodes are PinRefs and whose edges are connections.

    Edges come from resolved wires when present; otherwise each net
    contributes a chain over its (sorted) pins so connected components of the
    graph match nets either way.
    """
    g = nx.Graph()
    for net in project.nets.values():
        for pin in net.pins:
            g.add_node(pin, net_id=net.id)
    if project.wires:
        for wire in project.wires.values():
            g.add_edge(wire.source, wire.target, wire_id=wire.id, net_id=wire.net_id)
    else:
        for net_id in sorted(project.nets):
            pins = sorted(project.nets[net_id].pins)
            for a, b in pairwise(pins):
                g.add_edge(a, b, net_id=net_id)
    return g


def nets_from_graph(graph: nx.Graph) -> list[set[PinRef]]:
    """Connected components of the pin graph, deterministically ordered."""
    comps = [set(c) for c in nx.connected_components(graph)]
    return sorted(comps, key=lambda c: min(c))


def cross_references(project: Project, pin_ref: PinRef) -> list[PinRef]:
    """Other PinRefs sharing a net with ``pin_ref`` (sorted, excludes itself)."""
    net = project.net_of(pin_ref)
    if net is None:
        return []
    return sorted(p for p in net.pins if p != pin_ref)
