"""Wiring / backplate diagram — a top view rendered straight from geometry.

World coordinates are millimetres with Y up; SVG has Y down, so points pass
through a flip. Views never mutate the model: wire geometry uses the routed
``path`` when the router has run, else the straight terminal-to-terminal line.
"""

from __future__ import annotations

from ..model.component import world_pin_position
from ..model.geometry import BoundingBox
from ..model.project import Project
from . import svg_util as svg
from .connection_list import _wires

MARGIN = 20.0


def render_wiring(project: Project) -> str:
    if project.surfaces:
        xs = [s.origin[0] + s.size[0] for s in project.surfaces.values()]
        ys = [s.origin[1] + s.size[1] for s in project.surfaces.values()]
        world_w, world_h = max(xs), max(ys)
    else:
        world_w = world_h = 600.0

    canvas = svg.Canvas(world_w + 2 * MARGIN, world_h + 2 * MARGIN)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x + MARGIN, world_h - y + MARGIN)

    # Mounting surfaces.
    for sid in sorted(project.surfaces):
        s = project.surfaces[sid]
        x0, y0 = pt(s.origin[0], s.origin[1] + s.size[1])
        canvas.add(
            svg.rect(x0, y0, s.size[0], s.size[1], fill="#f2f2f2", stroke="#888", stroke_width=1)
        )
        canvas.add(svg.text(x0 + 4, y0 + 12, sid, font_size=10, fill="#888"))

    # Ducts: light channel rectangles along each centerline segment.
    for did in sorted(project.ducts):
        duct = project.ducts[did]
        half = duct.width_mm / 2.0
        for a, b in zip(duct.centerline, duct.centerline[1:]):
            lo_x, hi_x = min(a[0], b[0]), max(a[0], b[0])
            lo_y, hi_y = min(a[1], b[1]), max(a[1], b[1])
            if lo_y == hi_y:  # horizontal run
                x0, y0 = pt(lo_x, lo_y + half)
                w, h = hi_x - lo_x, duct.width_mm
            elif lo_x == hi_x:  # vertical run
                x0, y0 = pt(lo_x - half, hi_y)
                w, h = duct.width_mm, hi_y - lo_y
            else:  # diagonal run: draw as a thick line instead of a rect
                canvas.add(
                    svg.line(
                        *pt(a[0], a[1]),
                        *pt(b[0], b[1]),
                        stroke="#dce8f2",
                        stroke_width=duct.width_mm,
                    )
                )
                continue
            canvas.add(svg.rect(x0, y0, w, h, fill="#dce8f2", stroke="#9db8cc", stroke_width=0.5))
        first = duct.centerline[0]
        fx, fy = pt(first[0], first[1])
        canvas.add(svg.text(fx + 2, fy - 2, did, font_size=8, fill="#9db8cc"))

    # Components as world AABBs, labeled with their tag.
    for c in project.iter_components():
        part = project.part_of(c)
        lo, hi = BoundingBox(part.size).world_aabb(c.placement)
        x0, y0 = pt(float(lo[0]), float(hi[1]))
        w, h = float(hi[0] - lo[0]), float(hi[1] - lo[1])
        canvas.add(svg.rect(x0, y0, w, h, fill="#fff", stroke="#333", stroke_width=1.5))
        canvas.add(
            svg.text(x0 + w / 2, y0 + h / 2, c.tag, font_size=12, text_anchor="middle", fill="#333")
        )

    # Wires: routed path when present, else straight; labeled with the number.
    for w in sorted(_wires(project), key=lambda w: w.number):
        if w.path is not None:
            path_pts = [(p[0], p[1]) for p in w.path]
        else:
            a = world_pin_position(project.components[w.source[0]], w.source[1], project.library)
            b = world_pin_position(project.components[w.target[0]], w.target[1], project.library)
            path_pts = [(float(a[0]), float(a[1])), (float(b[0]), float(b[1]))]
        canvas.add(svg.polyline([pt(x, y) for x, y in path_pts], stroke=w.color, stroke_width=1))
        mid = path_pts[len(path_pts) // 2]
        mx, my = pt(mid[0], mid[1])
        canvas.add(svg.text(mx + 2, my - 2, w.number, font_size=8, fill=w.color))

    # Terminals last so the dots sit on top of the wires.
    for c in project.iter_components():
        for tag, pin in c.pin_refs(project.library):
            pos = world_pin_position(c, pin, project.library)
            x, y = pt(float(pos[0]), float(pos[1]))
            canvas.add(svg.circle(x, y, 1.5, fill="#c00"))

    return canvas.to_svg()
