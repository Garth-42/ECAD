"""Route resolved wires through the duct network to get real lengths.

The routing graph is built once per project: duct waypoints become nodes and
consecutive waypoints become edges. Ducts are joined wherever they meet —
at shared (or nearly shared) waypoints, where one duct ends part-way along
another (a T), and where two ducts cross (an X). Each wire terminal is dropped
onto the nearest point of the nearest duct segment. Shortest paths over that
graph give the wire lengths (plus installation slack).

With no usable duct network the router uses the straight line between
terminals. If ducts exist but a wire's two ends land on duct sections that are
not connected to each other, that wire also falls back to a straight line and
its id is returned so callers can warn — a straight line is usually a serious
underestimate.

This module is one of the two sanctioned model writers: it sets
``wire.length_mm`` and ``wire.path`` and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import networkx as nx
import numpy as np

from ..model.component import world_pin_position
from ..model.connectivity import Wire, natural_key
from ..model.project import Project

FIXED_SLACK_MM = 50.0
SLACK_FRACTION = 0.10
# Duct points closer than this are considered joined.
JOIN_TOLERANCE_MM = 1.0

Point = tuple[float, float, float]

# Graph node names for the two ends of the wire being routed. Every other node
# is a coordinate tuple, so these never collide.
_SRC = "SRC"
_DST = "DST"


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
    try:
        return world_pin_position(component, pin_ref[1], project.library)
    except KeyError as exc:  # unknown part or pin
        raise ValueError(f"wire endpoint {pin_ref[0]}:{pin_ref[1]}: {exc.args[0]}") from exc


def _project_onto_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return a
    t = float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
    return a + t * ab


def _closest_points(
    a0: np.ndarray, a1: np.ndarray, b0: np.ndarray, b1: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Closest pair of points between segments ``a0-a1`` and ``b0-b1``.

    Solves the unconstrained line-line problem, then re-projects each
    candidate onto the other segment; two passes are enough for the clamped
    answer. Parallel segments start from ``a0``.
    """
    da, db = a1 - a0, b1 - b0
    r = a0 - b0
    aa, bb, ab = float(da @ da), float(db @ db), float(da @ db)
    denom = aa * bb - ab * ab
    if denom > 1e-12:
        s = float(np.clip((ab * float(db @ r) - bb * float(da @ r)) / denom, 0.0, 1.0))
    else:
        s = 0.0
    pa = a0 + s * da
    pb = _project_onto_segment(pa, b0, b1)
    pa = _project_onto_segment(pb, a0, a1)
    pb = _project_onto_segment(pa, b0, b1)
    return pa, pb


def _node(p: np.ndarray) -> Point:
    return (float(p[0]), float(p[1]), float(p[2]))


def _duct_graph(project: Project) -> nx.Graph:
    """Nodes = duct waypoints and junction points; edges weighted by distance."""
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    for duct_id in sorted(project.ducts):
        pts = [np.asarray(p, dtype=float) for p in project.ducts[duct_id].centerline]
        # A duct needs two waypoints to have any run; fewer contributes nothing.
        segments.extend((a, b) for a, b in pairwise(pts) if not np.array_equal(a, b))

    # Every segment is split where another segment touches or crosses it, so
    # T- and X-junctions become graph nodes that paths can turn at.
    splits: list[list[np.ndarray]] = [[a, b] for a, b in segments]
    for i, (a0, a1) in enumerate(segments):
        for j in range(i + 1, len(segments)):
            b0, b1 = segments[j]
            pa, pb = _closest_points(a0, a1, b0, b1)
            if float(np.linalg.norm(pa - pb)) <= JOIN_TOLERANCE_MM:
                splits[i].append(pa)
                splits[j].append(pb)

    g = nx.Graph()
    for (a, b), points in zip(segments, splits, strict=True):
        ab = b - a
        ordered = sorted(points, key=lambda p: float((p - a) @ ab))
        for p, q in pairwise(ordered):
            u, v = _node(p), _node(q)
            if u != v:
                g.add_edge(u, v, weight=float(np.linalg.norm(q - p)))

    # Stitch nodes that coincide within tolerance (junction points computed on
    # two different segments, or duct ends that nearly meet).
    nodes = sorted(g.nodes)
    for i, u in enumerate(nodes):
        for v in nodes[i + 1 :]:
            d = float(np.linalg.norm(np.subtract(u, v)))
            if d <= JOIN_TOLERANCE_MM:
                g.add_edge(u, v, weight=d)
    return g


def _attach_terminal(g: nx.Graph, node: str, pos: np.ndarray) -> None:
    """Connect a terminal node to the nearest point of the nearest duct segment."""
    # Only duct edges are candidates: edges touching the other terminal are
    # skipped (and must be, since str and tuple nodes do not sort together).
    duct_edges = sorted(
        (u, v) if u <= v else (v, u)
        for u, v in g.edges
        if not isinstance(u, str) and not isinstance(v, str)
    )
    best: tuple[float, np.ndarray, Point, Point] | None = None
    for u, v in duct_edges:
        foot = _project_onto_segment(pos, np.asarray(u), np.asarray(v))
        d = float(np.linalg.norm(pos - foot))
        if best is None or d < best[0]:
            best = (d, foot, u, v)
    if best is None:
        raise ValueError("duct graph has no segments to attach to")
    d, foot, u, v = best
    foot_node = _node(foot)
    if foot_node not in g:
        # Split the segment at the foot point so paths can turn there.
        w = g.edges[u, v]["weight"]
        du = float(np.linalg.norm(foot - np.asarray(u)))
        g.add_edge(u, foot_node, weight=du)
        g.add_edge(foot_node, v, weight=max(w - du, 0.0))
    g.add_edge(node, foot_node, weight=d)


def _slack(run_length: float) -> float:
    return max(FIXED_SLACK_MM, SLACK_FRACTION * run_length)


def route_wires(project: Project) -> list[str]:
    """Set ``length_mm`` and ``path`` on every resolved wire (in place).

    Returns the ids of wires that could not be routed through the duct
    network even though ducts exist (their ends sit on disconnected duct
    sections); those wires get the straight-line length. The list is empty
    when everything routed, and when the project has no ducts at all.
    """
    if not project.wires:
        raise ValueError("no wires to route — run resolve_wires() first")

    base = _duct_graph(project) if project.ducts else None
    if base is not None and base.number_of_edges() == 0:
        base = None  # only degenerate ducts: same as having none

    unrouted: list[str] = []
    for wire in project.iter_wires():
        src = _terminal_position(project, wire.source)
        dst = _terminal_position(project, wire.target)

        routed: list[Point] | None = None
        if base is not None:
            g = base.copy()
            _attach_terminal(g, _SRC, src)
            _attach_terminal(g, _DST, dst)
            try:
                node_path = nx.shortest_path(g, _SRC, _DST, weight="weight")
                pts = [src] + [np.asarray(n) for n in node_path[1:-1]] + [dst]
                routed = [_node(p) for p in pts]
            except nx.NetworkXNoPath:
                unrouted.append(wire.id)

        if routed is None:
            # Fallback: straight run between the terminals.
            routed = [_node(src), _node(dst)]

        run = sum(float(np.linalg.norm(np.subtract(b, a))) for a, b in pairwise(routed))
        wire.path = routed
        wire.length_mm = run + _slack(run)
    return unrouted


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
    return sorted(rows, key=lambda r: natural_key(r.number))


def render_cut_list(project: Project) -> str:
    lines = [
        f"CUT LIST — {project.name}",
        "",
        f"{'WIRE':<6} {'FROM':<10} {'TO':<10} {'LENGTH mm':>10}  {'COLOR':<8} GAUGE",
    ]
    for r in cut_list(project):
        lines.append(
            f"{r.number:<6} {r.source:<10} {r.target:<10} {r.length_mm:>10.1f}  "
            f"{r.color:<8} {r.gauge}"
        )
    return "\n".join(lines) + "\n"
