"""Route resolved wires through the duct network to get real lengths.

The routing graph is built once per project: duct waypoints become nodes,
consecutive waypoints become edges, ducts that share (or nearly share) an
endpoint are stitched together, and each wire terminal is dropped onto the
nearest point of the nearest duct segment. Shortest paths over that graph give
the wire lengths (plus installation slack). With no reachable duct network the
router falls back to the straight line between terminals.

This module is one of the two sanctioned model writers: it sets
``wire.length_mm`` and ``wire.path`` and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from ..model.component import world_pin_position
from ..model.connectivity import Wire
from ..model.project import Project

FIXED_SLACK_MM = 50.0
SLACK_FRACTION = 0.10
# Duct endpoints closer than this are considered joined.
JOIN_TOLERANCE_MM = 1.0

Point = tuple[float, float, float]


@dataclass(frozen=True)
class CutListRow:
    number: str
    source: str  # "TAG:PIN"
    target: str
    length_mm: float
    color: str
    gauge: str


def straight_line_length(project: Project, wire: Wire) -> float:
    """Euclidean distance between the wire's terminal world positions."""
    a = _terminal_position(project, wire.source)
    b = _terminal_position(project, wire.target)
    return float(np.linalg.norm(a - b))


def _terminal_position(project: Project, pin_ref: tuple[str, str]) -> np.ndarray:
    component = project.components.get(pin_ref[0])
    if component is None:
        raise ValueError(f"wire endpoint {pin_ref[0]}:{pin_ref[1]} references unknown component")
    return world_pin_position(component, pin_ref[1], project.library)


def _project_onto_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return a
    t = float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
    return a + t * ab


def _duct_graph(project: Project) -> nx.Graph:
    """Nodes = duct waypoints (plus stitch points); edges weighted by distance."""
    g = nx.Graph()
    for duct_id in sorted(project.ducts):
        pts = [np.asarray(p, dtype=float) for p in project.ducts[duct_id].centerline]
        for a, b in zip(pts, pts[1:]):
            g.add_edge(tuple(a), tuple(b), weight=float(np.linalg.norm(b - a)))
    # Stitch ducts that share or nearly share nodes.
    nodes = sorted(g.nodes)
    for i, u in enumerate(nodes):
        for v in nodes[i + 1 :]:
            if u != v:
                d = float(np.linalg.norm(np.subtract(u, v)))
                if d <= JOIN_TOLERANCE_MM:
                    g.add_edge(u, v, weight=d)
    return g


def _attach_terminal(g: nx.Graph, node: object, pos: np.ndarray) -> None:
    """Connect a terminal node to the nearest point of the nearest duct segment."""
    best: tuple[float, np.ndarray, tuple, tuple] | None = None
    for u, v in sorted(g.edges):
        if isinstance(u, str) or isinstance(v, str):
            continue  # skip terminal attachment edges
        foot = _project_onto_segment(pos, np.asarray(u), np.asarray(v))
        d = float(np.linalg.norm(pos - foot))
        if best is None or d < best[0]:
            best = (d, foot, u, v)
    assert best is not None
    d, foot, u, v = best
    foot_node = tuple(float(x) for x in foot)
    if foot_node not in g:
        # Split the segment at the foot point so paths can turn there.
        w = g.edges[u, v]["weight"]
        du = float(np.linalg.norm(foot - np.asarray(u)))
        g.add_edge(u, foot_node, weight=du)
        g.add_edge(foot_node, v, weight=max(w - du, 0.0))
    g.add_edge(node, foot_node, weight=d)


def _slack(run_length: float) -> float:
    return max(FIXED_SLACK_MM, SLACK_FRACTION * run_length)


def route_wires(project: Project) -> None:
    """Set ``length_mm`` and ``path`` on every resolved wire (in place)."""
    if not project.wires:
        raise ValueError("no wires to route — run resolve_wires() first")

    base = _duct_graph(project) if project.ducts else None

    for wire in project.iter_wires():
        src = _terminal_position(project, wire.source)
        dst = _terminal_position(project, wire.target)

        routed: list[Point] | None = None
        if base is not None:
            g = base.copy()
            _attach_terminal(g, "SRC", src)
            _attach_terminal(g, "DST", dst)
            try:
                node_path = nx.shortest_path(g, "SRC", "DST", weight="weight")
                pts = [src] + [np.asarray(n) for n in node_path[1:-1]] + [dst]
                routed = [tuple(float(x) for x in p) for p in pts]
            except nx.NetworkXNoPath:  # pragma: no cover - disconnected network
                routed = None

        if routed is None:
            # Fallback: straight run between the terminals.
            routed = [tuple(float(x) for x in src), tuple(float(x) for x in dst)]

        run = sum(float(np.linalg.norm(np.subtract(b, a))) for a, b in zip(routed, routed[1:]))
        wire.path = routed
        wire.length_mm = run + _slack(run)


def cut_list(project: Project) -> list[CutListRow]:
    """Cut list rows sorted by wire number; requires routed wires."""
    rows = []
    for wire in project.iter_wires():
        if wire.length_mm is None:
            raise ValueError(f"wire {wire.id} has no length — run route_wires() first")
        rows.append(
            CutListRow(
                number=wire.number,
                source=f"{wire.source[0]}:{wire.source[1]}",
                target=f"{wire.target[0]}:{wire.target[1]}",
                length_mm=round(wire.length_mm, 1),
                color=wire.color,
                gauge=wire.gauge,
            )
        )
    return sorted(rows, key=lambda r: r.number)


def render_cut_list(project: Project) -> str:
    lines = [
        f"CUT LIST — {project.name}",
        "",
        f"{'WIRE':<6} {'FROM':<10} {'TO':<10} {'LENGTH mm':>10}  {'COLOR':<8} GAUGE",
    ]
    for r in cut_list(project):
        lines.append(
            f"{r.number:<6} {r.source:<10} {r.target:<10} {r.length_mm:>10.1f}  {r.color:<8} {r.gauge}"
        )
    return "\n".join(lines) + "\n"
