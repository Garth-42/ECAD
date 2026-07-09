"""M6: duct-graph routing — lengths, slack, fallback, cut list."""

import numpy as np
import pytest

from examples.motor_start_stop import build_project

from panelkit.model.component import world_pin_position
from panelkit.model.project import Project
from panelkit.routing.resolve import resolve_wires
from panelkit.routing.router import (
    FIXED_SLACK_MM,
    cut_list,
    render_cut_list,
    route_wires,
    straight_line_length,
)


@pytest.fixture()
def routed_example() -> Project:
    p = build_project()
    resolve_wires(p)
    route_wires(p)
    return p


class TestRouting:
    def test_every_wire_gets_length_and_path(self, routed_example: Project) -> None:
        for w in routed_example.wires.values():
            assert w.length_mm is not None and w.length_mm > 0
            assert w.path is not None and len(w.path) >= 2

    def test_routed_length_never_below_straight_line(self, routed_example: Project) -> None:
        for w in routed_example.wires.values():
            assert w.length_mm >= straight_line_length(routed_example, w)

    def test_duct_detour_strictly_longer_than_straight_line(self, routed_example: Project) -> None:
        # Wires that must travel the wireway (e.g. contactor coil return A2 to
        # X1:7 across the panel) come out strictly longer than the crow flies,
        # even net of slack — proof the router used the ducts.
        detoured = [
            w
            for w in routed_example.wires.values()
            if w.length_mm > 1.02 * (straight_line_length(routed_example, w) + FIXED_SLACK_MM)
        ]
        assert detoured, "expected at least one wire to detour through the ducts"

    def test_path_endpoints_are_terminals(self, routed_example: Project) -> None:
        for w in routed_example.wires.values():
            src = routed_example.components[w.source[0]]
            dst = routed_example.components[w.target[0]]
            assert np.allclose(
                w.path[0], world_pin_position(src, w.source[1], routed_example.library)
            )
            assert np.allclose(
                w.path[-1], world_pin_position(dst, w.target[1], routed_example.library)
            )

    def test_deterministic(self) -> None:
        def run() -> dict:
            p = build_project()
            resolve_wires(p)
            route_wires(p)
            return {k: (w.length_mm, tuple(w.path)) for k, w in p.wires.items()}

        assert run() == run()


class TestFallback:
    def test_no_ducts_falls_back_to_straight_line(self) -> None:
        p = build_project()
        p.ducts.clear()
        resolve_wires(p)
        route_wires(p)
        for w in p.wires.values():
            straight = straight_line_length(p, w)
            assert len(w.path) == 2
            assert w.length_mm == pytest.approx(straight + max(FIXED_SLACK_MM, 0.10 * straight))

    def test_route_before_resolve_fails_loudly(self) -> None:
        p = build_project()
        with pytest.raises(ValueError, match="resolve"):
            route_wires(p)


class TestCutList:
    def test_sorted_by_wire_number(self, routed_example: Project) -> None:
        rows = cut_list(routed_example)
        assert len(rows) == 21
        assert [r.number for r in rows] == sorted(r.number for r in rows)

    def test_requires_routing(self) -> None:
        p = build_project()
        resolve_wires(p)
        with pytest.raises(ValueError, match="route"):
            cut_list(p)

    def test_render(self, routed_example: Project) -> None:
        text = render_cut_list(routed_example)
        assert "CUT LIST" in text and "X1:1" in text
