"""Connectivity: nets, wires, and the pin-adjacency graph."""

from __future__ import annotations

from dataclasses import dataclass, field
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


def build_graph(project: "Project") -> nx.Graph:
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
            for a, b in zip(pins, pins[1:]):
                g.add_edge(a, b, net_id=net_id)
    return g


def nets_from_graph(graph: nx.Graph) -> list[set[PinRef]]:
    """Connected components of the pin graph, deterministically ordered."""
    comps = [set(c) for c in nx.connected_components(graph)]
    return sorted(comps, key=lambda c: min(c))


def cross_references(project: "Project", pin_ref: PinRef) -> list[PinRef]:
    """Other PinRefs sharing a net with ``pin_ref`` (sorted, excludes itself)."""
    net = project.net_of(pin_ref)
    if net is None:
        return []
    return sorted(p for p in net.pins if p != pin_ref)
