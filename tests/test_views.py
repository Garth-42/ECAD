"""M5/M7: text views (netlist, connections, BOM, terminal plan) — data + render."""

from examples.motor_start_stop import build_project

import pytest

from panelkit.model.project import Project
from panelkit.views.bom import bom, render_bom
from panelkit.views.connection_list import connection_list, render_connection_list
from panelkit.views.netlist import netlist, render_netlist
from panelkit.views.terminal_plan import render_terminal_plan, terminal_plan


@pytest.fixture()
def example() -> Project:
    return build_project()


class TestNetlist:
    def test_all_nets_listed(self, example: Project) -> None:
        rows = netlist(example)
        assert len(rows) == len(example.nets) == 16
        by_id = {r[0]: r for r in rows}
        assert by_id["n22"][1] == "COIL"
        assert by_id["n22"][2] == [("K1", "14"), ("K1", "A1"), ("S2", "4")]

    def test_render(self, example: Project) -> None:
        text = render_netlist(example)
        assert "COIL" in text and "K1:A1" in text


class TestConnectionList:
    def test_view_does_not_mutate_model(self, example: Project) -> None:
        assert example.wires == {}
        rows = connection_list(example)
        assert len(rows) == 21
        assert example.wires == {}  # view computed wires locally

    def test_rows_sorted_by_number(self, example: Project) -> None:
        numbers = [r.number for r in connection_list(example)]
        assert numbers == sorted(numbers)

    def test_render(self, example: Project) -> None:
        text = render_connection_list(example)
        assert "S1:2" in text and "0.75 mm2" in text


class TestBom:
    def test_counts_for_canonical_example(self, example: Project) -> None:
        rows = bom(example)
        assert sum(r.quantity for r in rows) == 7  # seven components
        by_part = {r.part_number: r for r in rows}
        assert by_part["LC1D09P7"].quantity == 1
        assert by_part["LC1D09P7"].tags == ("K1",)
        assert by_part["XB4BA42"].tags == ("S1",)
        assert len(rows) == 7  # all distinct part numbers

    def test_groups_repeated_parts(self, small_project: Project) -> None:
        rows = bom(small_project)
        assert {r.part_number for r in rows} == {"XB4BA42", "XB4BA31"}

    def test_render(self, example: Project) -> None:
        text = render_bom(example)
        assert "GV2ME14" in text and "Schneider Electric" in text


class TestTerminalPlan:
    def test_every_x1_point_planned(self, example: Project) -> None:
        rows = terminal_plan(example)
        assert [r.point for r in rows] == [str(i) for i in range(1, 9)]
        assert all(r.terminal == "X1" for r in rows)

    def test_star_far_ends(self, example: Project) -> None:
        rows = {r.point: r for r in terminal_plan(example)}
        assert rows["1"].connected == ("F1:2", "M1:U")
        assert rows["7"].connected == ("K1:A2",)
        assert rows["1"].net_name == "T1"

    def test_render(self, example: Project) -> None:
        text = render_terminal_plan(example)
        assert "[X1]" in text and "M1:U" in text
