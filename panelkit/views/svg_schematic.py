"""Schematic (ladder-style) SVG view.

Deterministic, rule-based layout — intentionally plain (see spec 9.1):

- Two horizontal power rails frame the drawing; nets whose names look like a
  control line / return snap onto them.
- Every component is one vertical rung (a column), ordered by tag. Its
  category picks a small symbol glyph; pins sit on the symbol's top or bottom
  edge according to the pin's local Y in the part definition.
- Every other net gets a horizontal bus level below the symbols; each wire is
  an orthogonal polyline pin -> bus -> pin, jogging around the symbol body
  when a pin exits on the wrong side. Wires carry their number; pins whose
  net appears elsewhere carry a cross-reference.

All positions land on a 10 mm grid except pin stubs, which follow the part's
pin spacing.
"""

from __future__ import annotations

from ..model.connectivity import cross_references
from ..model.project import Project
from . import svg_util as svg
from .connection_list import _wires

MARGIN = 20.0
PITCH = 100.0  # one rung (column) per component
SYM_W = 60.0
RAIL_TOP_Y = 40.0
SYM_TOP_Y = 80.0
SYM_BOT_Y = 160.0
BUS_BAND_Y = 200.0
BUS_STEP = 10.0
STUB = 10.0

# NOTE: the model has no notion of "rails"; the spec is silent on how the two
# power rails map to nets, so nets are matched by conventional signal names.
TOP_RAIL_NAMES = ("CTRL_L", "L", "L1", "24V", "+24V")
BOTTOM_RAIL_NAMES = ("CTRL_N", "N", "0V", "RET", "PE")


def _rail_net(project: Project, names: tuple[str, ...]) -> str | None:
    for name in names:  # earlier names take priority (CTRL_L beats L1)
        for net in project.iter_nets():
            if net.name == name:
                return net.id
    return None


def _symbol_glyph(category: str, cx: float, cy: float) -> list[str]:
    """Small category glyph drawn inside the symbol body."""
    match category:
        case "contactor" | "relay":
            return [svg.circle(cx, cy, 8, fill="none", stroke="#333")]
        case "motor":
            return [
                svg.circle(cx, cy, 12, fill="none", stroke="#333"),
                svg.text(cx, cy + 3, "M", font_size=10, text_anchor="middle"),
            ]
        case "pushbutton":
            return [
                svg.line(cx - 8, cy, cx + 8, cy, stroke="#333"),
                svg.line(cx, cy - 10, cx, cy, stroke="#333"),
            ]
        case "breaker" | "fuse":
            return [svg.line(cx - 8, cy + 8, cx + 8, cy - 8, stroke="#333")]
        case "overload":
            return [
                svg.polyline(
                    [(cx - 8, cy), (cx - 3, cy - 6), (cx + 3, cy + 6), (cx + 8, cy)],
                    stroke="#333",
                )
            ]
        case "terminal_block":
            return [svg.circle(cx, cy, 3, fill="none", stroke="#333")]
        case _:
            return []


def render_schematic(project: Project) -> str:
    tags = sorted(project.components)
    top_rail = _rail_net(project, TOP_RAIL_NAMES)
    bottom_rail = _rail_net(project, BOTTOM_RAIL_NAMES)
    other_nets = [n for n in sorted(project.nets) if n not in (top_rail, bottom_rail)]

    bus_y = {net_id: BUS_BAND_Y + i * BUS_STEP for i, net_id in enumerate(other_nets)}
    rail_bot_y = BUS_BAND_Y + len(other_nets) * BUS_STEP + 20.0
    if top_rail is not None:
        bus_y[top_rail] = RAIL_TOP_Y
    if bottom_rail is not None:
        bus_y[bottom_rail] = rail_bot_y

    width = 2 * MARGIN + max(len(tags), 1) * PITCH
    canvas = svg.Canvas(width, rail_bot_y + 40.0)

    # Power rails.
    for y, net_id, fallback in (
        (RAIL_TOP_Y, top_rail, "L"),
        (rail_bot_y, bottom_rail, "N"),
    ):
        canvas.add(svg.line(MARGIN, y, width - MARGIN, y, stroke="#000", stroke_width=2))
        label = project.nets[net_id].name if net_id else fallback
        canvas.add(svg.text(MARGIN, y - 4, label, font_size=10, font_weight="bold"))

    # Symbols: one rung per component, pins on the top/bottom symbol edge.
    pin_pos: dict[tuple[str, str], tuple[float, float, bool]] = {}
    for i, tag in enumerate(tags):
        component = project.components[tag]
        part = project.part_of(component)
        col_x = MARGIN + (i + 0.5) * PITCH
        x0 = col_x - SYM_W / 2
        canvas.add(
            svg.rect(x0, SYM_TOP_Y, SYM_W, SYM_BOT_Y - SYM_TOP_Y, fill="#fff", stroke="#333")
        )
        canvas.add(svg.text(x0, SYM_TOP_Y - 24, tag, font_size=11, font_weight="bold"))
        for el in _symbol_glyph(part.category, col_x, (SYM_TOP_Y + SYM_BOT_Y) / 2):
            canvas.add(el)

        half_h = part.size[1] / 2
        top_pins = [p.name for p in part.pins if p.local_pos[1] >= half_h]
        bot_pins = [p.name for p in part.pins if p.local_pos[1] < half_h]
        for names, edge_y, is_top in ((top_pins, SYM_TOP_Y, True), (bot_pins, SYM_BOT_Y, False)):
            for j, name in enumerate(names):
                px = x0 + (j + 1) * SYM_W / (len(names) + 1)
                pin_pos[(tag, name)] = (px, edge_y, is_top)
                canvas.add(svg.circle(px, edge_y, 1.5, fill="#333"))
                ly = edge_y + (8 if not is_top else -4)
                canvas.add(svg.text(px + 1, ly, name, font_size=6, fill="#555"))

    # Cross-references: pins whose net also appears elsewhere.
    for (tag, name), (px, py, is_top) in sorted(pin_pos.items()):
        refs = [r for r in cross_references(project, (tag, name)) if r[0] != tag]
        if not refs:
            continue
        ref_text = " ".join(f"→{t}:{p}" for t, p in refs)
        ty = py - 14 if is_top else py + 16
        rot = -90 if is_top else 90
        canvas.add(
            svg.text(
                px + 2,
                ty,
                ref_text,
                font_size=5,
                fill="#777",
                transform=f"rotate({rot} {px + 2} {ty})",
            )
        )

    # Wires: orthogonal pin -> bus -> pin polylines with wrong-side jogs.
    jog_count: dict[tuple[int, int], int] = {}

    def exit_points(ref: tuple[str, str], y_bus: float) -> list[tuple[float, float]]:
        px, py, is_top = pin_pos[ref]
        col = int((px - MARGIN) // PITCH)
        col_x = MARGIN + (col + 0.5) * PITCH
        if is_top and y_bus <= SYM_TOP_Y - STUB:
            return [(px, py), (px, y_bus)]
        if not is_top and y_bus >= SYM_BOT_Y + STUB:
            return [(px, py), (px, y_bus)]
        # Wrong side: leave the pin, then run around the symbol body.
        clear_y = SYM_TOP_Y - STUB if is_top else SYM_BOT_Y + STUB
        side = -1 if px <= col_x else 1
        n = jog_count.get((col, side), 0)
        jog_count[(col, side)] = n + 1
        side_x = col_x + side * (SYM_W / 2 + 8 + 6 * n)
        return [(px, py), (px, clear_y), (side_x, clear_y), (side_x, y_bus)]

    for wire in sorted(_wires(project), key=lambda w: w.number):
        if wire.source not in pin_pos or wire.target not in pin_pos:
            continue  # endpoint on a component with no symbol (defensive)
        y_bus = bus_y[wire.net_id]
        a = exit_points(wire.source, y_bus)
        b = exit_points(wire.target, y_bus)
        points = a + list(reversed(b))
        canvas.add(svg.polyline(points, stroke=wire.color, stroke_width=1))
        mx = (a[-1][0] + b[-1][0]) / 2
        canvas.add(
            svg.text(mx, y_bus - 2, wire.number, font_size=7, fill=wire.color, text_anchor="middle")
        )

    return canvas.to_svg()
