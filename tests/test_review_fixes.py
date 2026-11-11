"""Regression tests for the code-review fixes.

Each class covers one bug that previously crashed or silently produced a
wrong answer; the docstrings say what used to happen.
"""

from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from examples.motor_start_stop import build_project, build_project_with_harness
from panelkit.cli import main
from panelkit.integrations.wireviz.export import to_wireviz_dict
from panelkit.library.parts import PartLibrary
from panelkit.model.colors import css_colors, to_iec_color
from panelkit.model.component import Component
from panelkit.model.connectivity import Net, natural_key, wires_consistent
from panelkit.model.geometry import Placement
from panelkit.model.harness import select_harness
from panelkit.model.layout import Duct
from panelkit.model.project import Project
from panelkit.persistence import load_project, save_project
from panelkit.routing.resolve import compute_wires, resolve_wires
from panelkit.routing.router import cut_list, route_wires, straight_line_length
from panelkit.rules.checks import clearance_violations, validate
from panelkit.views.connection_list import connection_list
from panelkit.views.svg_wiring import render_wiring


def two_buttons(library: PartLibrary, ducts: list[list[tuple[float, float, float]]]) -> Project:
    """S1 at x=50 and S2 at x=150, one net between them, plus the given ducts."""
    p = Project(name="two", library=library)
    p.add_component(Component("S1", "XB4BA42", Placement((50.0, 50.0, 0.0))))
    p.add_component(Component("S2", "XB4BA31", Placement((150.0, 50.0, 0.0))))
    p.add_net(Net("n", "LINK", {("S1", "2"), ("S2", "3")}))
    for i, centerline in enumerate(ducts):
        p.add_duct(Duct(f"d{i}", centerline))
    return p


def codes(findings) -> set[str]:
    return {f.code for f in findings}


class TestRouterTerminalBeyondDuctEnd:
    """Used to raise TypeError: both pins project onto the same duct waypoint."""

    def test_routes_via_the_duct_end(self, library: PartLibrary) -> None:
        p = two_buttons(library, [[(500.0, 100.0, 0.0), (600.0, 100.0, 0.0)]])
        resolve_wires(p)
        assert route_wires(p) == []
        (wire,) = p.wires.values()
        assert (500.0, 100.0, 0.0) in wire.path
        assert wire.length_mm > straight_line_length(p, wire)


class TestRouterJunctions:
    """Ducts meeting in a T or an X used to be disconnected (straight-line fallback)."""

    def test_t_junction_matches_explicit_waypoints(self) -> None:
        explicit = build_project()
        resolve_wires(explicit)
        route_wires(explicit)

        tee = build_project()
        # Drop the shared mid waypoints: d_drop now ends part-way along both runs.
        tee.ducts["d_top"].centerline = [(20.0, 420.0, 0.0), (580.0, 420.0, 0.0)]
        tee.ducts["d_bot"].centerline = [(20.0, 60.0, 0.0), (580.0, 60.0, 0.0)]
        resolve_wires(tee)
        assert route_wires(tee) == []
        for wire_id, wire in tee.wires.items():
            assert wire.length_mm == pytest.approx(explicit.wires[wire_id].length_mm)

    def test_crossing_ducts_are_joined(self, library: PartLibrary) -> None:
        # A horizontal and a vertical duct that cross with no shared waypoint.
        p = two_buttons(
            library,
            [
                [(0.0, 300.0, 0.0), (400.0, 300.0, 0.0)],
                [(200.0, 0.0, 0.0), (200.0, 400.0, 0.0)],
            ],
        )
        p.components["S2"] = Component("S2", "XB4BA31", Placement((190.0, 20.0, 0.0)))
        p.components["S1"] = Component("S1", "XB4BA42", Placement((20.0, 290.0, 0.0)))
        resolve_wires(p)
        assert route_wires(p) == []
        (wire,) = p.wires.values()
        assert (200.0, 300.0, 0.0) in wire.path  # turned at the crossing

    def test_disconnected_ducts_are_reported(self, library: PartLibrary) -> None:
        p = two_buttons(
            library,
            [
                [(0.0, 60.0, 0.0), (80.0, 60.0, 0.0)],
                [(140.0, 60.0, 0.0), (300.0, 60.0, 0.0)],
            ],
        )
        resolve_wires(p)
        unrouted = route_wires(p)
        assert unrouted == list(p.wires)
        (wire,) = p.wires.values()
        assert len(wire.path) == 2  # straight-line fallback, but now reported

    def test_cli_warns_about_unrouted_wires(self, tmp_path: Path, capsys) -> None:
        p = two_buttons(
            PartLibrary.bundled(),
            [
                [(0.0, 60.0, 0.0), (80.0, 60.0, 0.0)],
                [(140.0, 60.0, 0.0), (300.0, 60.0, 0.0)],
            ],
        )
        save_project(p, tmp_path / "p.json")
        assert main(["route", str(tmp_path / "p.json")]) == 0
        assert "could not be routed" in capsys.readouterr().err


class TestDegenerateDucts:
    """Empty / single-point ducts used to raise AssertionError and IndexError."""

    @pytest.mark.parametrize("centerline", [[], [(1.0, 1.0, 0.0)]])
    def test_router_and_view_ignore_them(self, library: PartLibrary, centerline) -> None:
        p = two_buttons(library, [centerline])
        resolve_wires(p)
        assert route_wires(p) == []
        (wire,) = p.wires.values()
        assert len(wire.path) == 2
        ET.fromstring(render_wiring(p))
        assert "degenerate_duct" in codes(validate(p))


class TestNetReferenceRules:
    """validate used to say nothing about any of these."""

    def test_unknown_component_and_pin(self) -> None:
        p = build_project()
        p.nets["n04"].pins.add(("K1", "NOPE"))
        p.nets["n05"].pins.add(("ZZ9", "1"))
        dangling = [f for f in validate(p) if f.code == "dangling_pins"]
        assert [f.severity for f in dangling] == ["error", "error"]
        assert {f.refs[1] for f in dangling} == {"K1:NOPE", "ZZ9:1"}

    def test_pin_in_two_nets(self) -> None:
        p = build_project()
        p.nets["n06"].pins.add(("K1", "1"))  # already in n04
        (finding,) = [f for f in validate(p) if f.code == "pin_in_multiple_nets"]
        assert finding.severity == "error"
        assert finding.refs == ("K1:1", "n04", "n06")

    def test_clean_example_has_no_new_findings(self) -> None:
        new = {"dangling_pins", "pin_in_multiple_nets", "stale_wires", "degenerate_duct"}
        assert not new & codes(validate(build_project_with_harness()))


class TestValidateReportsInsteadOfCrashing:
    def _demo_data(self, tmp_path: Path, capsys) -> dict:
        main(["demo", "-o", str(tmp_path)])
        capsys.readouterr()
        return json.loads((tmp_path / "project.json").read_text())

    def test_all_unknown_parts_are_listed(self, tmp_path: Path, capsys) -> None:
        data = self._demo_data(tmp_path, capsys)
        data["components"]["K1"]["part_number"] = "BOGUS-1"
        data["components"]["Q1"]["part_number"] = "BOGUS-2"
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(data))
        assert main(["validate", str(bad)]) == 1
        out = capsys.readouterr().out
        assert "BOGUS-1" in out and "BOGUS-2" in out

    def test_strict_load_still_rejects_unknown_parts(self, tmp_path: Path, capsys) -> None:
        data = self._demo_data(tmp_path, capsys)
        data["components"]["K1"]["part_number"] = "BOGUS-1"
        for name in ("bad.json", "bad.db"):
            path = tmp_path / name
            if name.endswith(".json"):
                path.write_text(json.dumps(data))
            else:
                lenient = load_project(tmp_path / "bad.json", PartLibrary.bundled(), strict=False)
                save_project(lenient, path)
            with pytest.raises(ValueError, match="unknown part"):
                load_project(path, PartLibrary.bundled())
            assert "K1" in load_project(path, PartLibrary.bundled(), strict=False).components

    def test_bad_rotation_is_one_line_error(self, tmp_path: Path, capsys) -> None:
        data = self._demo_data(tmp_path, capsys)
        data["components"]["K1"]["placement"]["rotation_deg"] = 45
        bad = tmp_path / "rot.json"
        bad.write_text(json.dumps(data))
        assert main(["validate", str(bad)]) == 2
        assert "rotation_deg" in capsys.readouterr().err


class TestStaleWires:
    """Editing nets in a saved project used to leave views showing the old wires."""

    def _edited(self) -> Project:
        p = build_project_with_harness()
        p.nets["n21"].pins.discard(("K1", "13"))
        return p

    def test_detected(self) -> None:
        assert wires_consistent(build_project_with_harness())
        assert not wires_consistent(self._edited())
        assert "stale_wires" in codes(validate(self._edited()))

    def test_added_pin_is_also_stale(self) -> None:
        p = build_project_with_harness()
        p.nets["n20"].pins.add(("S2", "3"))
        assert not wires_consistent(p)

    def test_views_follow_the_nets(self) -> None:
        rows = connection_list(self._edited())
        assert not any("K1:13" in (r.source, r.target) for r in rows)

    def test_export_warns(self) -> None:
        _, warnings = to_wireviz_dict(self._edited(), "H1")
        assert "stale_wires" in codes(warnings)


class TestWirevizPins:
    def test_jumper_on_one_component_becomes_a_loop(self) -> None:
        """K1:14 -> K1:A1 used to fail the export as "not point-to-point"."""
        p = build_project()
        resolve_wires(p)
        route_wires(p)
        p.harnesses["H2"] = select_harness(p, {"K1", "S1", "S2"}, name="ctrl", harness_id="H2")
        doc, _ = to_wireviz_dict(p, "H2")
        # Positions: LC1D09P7 lists A1 first and 14 tenth.
        assert doc["connectors"]["K1"]["loops"] == [[10, 1]]
        assert len(doc["cables"]) == len(p.harnesses["H2"].wire_ids) - 1

    def test_connections_use_pin_positions_not_labels(self) -> None:
        """WireViz reads a numeric label like '13' as a position; send positions."""
        p = build_project()
        resolve_wires(p)
        route_wires(p)
        p.harnesses["H2"] = select_harness(p, {"K1", "S1", "S2"}, name="ctrl", harness_id="H2")
        doc, _ = to_wireviz_dict(p, "H2")
        k1_pins = [pin for conn in doc["connections"] for end in conn for pin in end.get("K1", [])]
        assert k1_pins and all(isinstance(pin, int) and 1 <= pin <= 10 for pin in k1_pins)
        assert 9 in k1_pins  # K1:13 is the ninth pin, not "13"

    def test_wire_ending_outside_harness_is_a_clear_error(self) -> None:
        p = build_project_with_harness()
        p.harnesses["H1"].component_tags.discard("M1")
        with pytest.raises(ValueError, match="M1"):
            to_wireviz_dict(p, "H1")


class TestNaturalOrder:
    def test_key(self) -> None:
        assert sorted(["1000", "101", "999"], key=natural_key) == ["101", "999", "1000"]
        assert sorted(["w1000", "w101"], key=natural_key) == ["w101", "w1000"]
        assert sorted(["12A", "2B", "X1"], key=natural_key) == ["2B", "12A", "X1"]

    def test_cut_list_orders_four_digit_numbers_last(self, library: PartLibrary) -> None:
        p = two_buttons(library, [])
        p.add_net(Net("n2", "L2", {("S1", "1"), ("S2", "4")}))
        resolve_wires(p)
        first, second = list(p.iter_wires())
        first.number, second.number = "1000", "999"
        route_wires(p)
        assert [r.number for r in cut_list(p)] == ["999", "1000"]
        assert [r.number for r in connection_list(p)] == ["999", "1000"]


class TestSvgEscaping:
    def test_quote_in_color_cannot_inject_an_attribute(self) -> None:
        p = build_project()
        resolve_wires(p)
        for wire in p.wires.values():
            wire.color = 'red" onload="alert(1)'
        root = ET.fromstring(render_wiring(p))
        assert not any("onload" in el.attrib for el in root.iter())


class TestColors:
    @pytest.mark.parametrize(
        ("raw", "code"),
        [("green/yellow", "GNYE"), ("Green-Yellow", "GNYE"), ("GNYE", "GNYE"), (" bu ", "BU")],
    )
    def test_iec(self, raw: str, code: str) -> None:
        assert to_iec_color(raw) == (code, True)

    def test_unknown_passes_through(self) -> None:
        assert to_iec_color("chartreuse") == ("chartreuse", False)
        assert css_colors("#ff8800") == ["#ff8800"]

    def test_css(self) -> None:
        assert css_colors("green/yellow") == ["green", "yellow"]
        assert css_colors("BU") == ["blue"]

    def test_two_colour_wire_renders_with_valid_strokes(self) -> None:
        p = build_project()
        resolve_wires(p)
        for wire in p.wires.values():
            wire.color = "green/yellow"
        strokes = {el.get("stroke") for el in ET.fromstring(render_wiring(p)).iter()}
        assert {"green", "yellow"} <= strokes
        assert "green/yellow" not in strokes


class TestPersistenceSafety:
    def test_failed_sqlite_save_keeps_the_old_file(self, tmp_path: Path) -> None:
        """save() used to delete the existing database before writing."""
        path = tmp_path / "p.db"
        good = build_project()
        save_project(good, path)
        bad = build_project()
        # Two dict keys holding the same tag violate the PRIMARY KEY mid-save.
        bad.components["DUP"] = bad.components["K1"]
        with pytest.raises(sqlite3.IntegrityError):
            save_project(bad, path)
        assert set(load_project(path, PartLibrary.bundled()).components) == set(good.components)
        assert list(tmp_path.iterdir()) == [path]  # no temp file left behind

    @pytest.mark.parametrize("name", ["p.json", "p.db"])
    def test_newer_format_version_is_refused(self, tmp_path: Path, name: str) -> None:
        path = tmp_path / name
        save_project(build_project(), path)
        if name.endswith(".json"):
            data = json.loads(path.read_text())
            data["format_version"] = 99
            path.write_text(json.dumps(data))
        else:
            con = sqlite3.connect(path)
            con.execute("UPDATE meta SET value = '99' WHERE key = 'format_version'")
            con.commit()
            con.close()
        with pytest.raises(ValueError, match="newer"):
            load_project(path, PartLibrary.bundled())

    def test_missing_field_names_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"components": {}}))
        with pytest.raises(ValueError, match=r"p\.json.*name"):
            load_project(path, PartLibrary.bundled())


class TestPartLibraryLoading:
    def test_missing_directory_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="nope"):
            PartLibrary().load_directory(tmp_path / "nope")

    def test_duplicate_part_number_in_one_directory(self, tmp_path: Path) -> None:
        part = {
            "part_number": "P1",
            "manufacturer": "m",
            "description": "d",
            "category": "other",
            "pins": [],
            "size": [1, 1, 1],
        }
        (tmp_path / "a.json").write_text(json.dumps(part))
        (tmp_path / "b.json").write_text(json.dumps(part))
        with pytest.raises(ValueError, match=r"a\.json and b\.json"):
            PartLibrary().load_directory(tmp_path)

    def test_later_directory_may_override(self, tmp_path: Path) -> None:
        lib = PartLibrary.bundled()
        original = lib.get("GV2ME14")
        data = json.loads(
            (Path(__file__).parent.parent / "panelkit/library/data/GV2ME14.json").read_text()
        )
        data["description"] = "overridden"
        (tmp_path / "GV2ME14.json").write_text(json.dumps(data))
        lib.load_directory(tmp_path)
        assert lib.get("GV2ME14").description == "overridden" != original.description


class TestCliErrors:
    @pytest.mark.parametrize(
        ("argv", "needle"),
        [
            (["bom", "{tmp}/nope.json"], "nope.json"),
            (["bom", "{demo}", "--library", "{tmp}/no-such-dir"], "parts directory not found"),
            (["export-wireviz", "{demo}", "--harness", "HX", "-o", "{tmp}/x.yml"], "HX"),
        ],
    )
    def test_one_line_error_and_exit_2(self, tmp_path: Path, capsys, argv, needle) -> None:
        main(["demo", "-o", str(tmp_path / "demo")])
        capsys.readouterr()
        subs = {"tmp": str(tmp_path), "demo": str(tmp_path / "demo" / "project.json")}
        assert main([a.format(**subs) for a in argv]) == 2
        err = capsys.readouterr().err
        assert err.startswith("error: ") and needle in err
        assert "Traceback" not in err

    def test_corrupt_json(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "p.json").write_text("{not json")
        assert main(["bom", str(tmp_path / "p.json")]) == 2
        assert "invalid JSON" in capsys.readouterr().err


class TestClearanceSurfaces:
    def test_different_surfaces_do_not_collide(self, library: PartLibrary) -> None:
        p = Project(name="c", library=library)
        p.add_component(Component("S1", "XB4BA42", Placement((0.0, 0.0, 0.0)), surface_id="door"))
        p.add_component(Component("S2", "XB4BA31", Placement((0.0, 0.0, 0.0)), surface_id="plate"))
        assert clearance_violations(p) == []
        p.components["S2"].surface_id = "door"
        assert len(clearance_violations(p)) == 1


class TestDaisyChainFollowsLayout:
    def test_nearest_neighbour_order(self, library: PartLibrary) -> None:
        """Alphabetical order would wire S1 -> S2 -> S3 and double back."""
        p = Project(name="chain", library=library)
        # S2 is the far one; S3 sits between S1 and S2.
        p.add_component(Component("S1", "XB4BA42", Placement((0.0, 0.0, 0.0))))
        p.add_component(Component("S2", "XB4BA42", Placement((400.0, 0.0, 0.0))))
        p.add_component(Component("S3", "XB4BA42", Placement((200.0, 0.0, 0.0))))
        p.add_net(Net("n", "N", {("S1", "1"), ("S2", "1"), ("S3", "1")}))
        wires = list(compute_wires(p).values())
        assert [(w.source[0], w.target[0]) for w in wires] == [("S1", "S3"), ("S3", "S2")]

    def test_unlocatable_pin_falls_back_to_sorted_order(self, library: PartLibrary) -> None:
        p = Project(name="chain", library=library)
        for tag in ("S1", "S2", "S3"):
            p.add_component(Component(tag, "XB4BA42", Placement((0.0, 0.0, 0.0))))
        p.add_net(Net("n", "N", {("S1", "1"), ("S2", "NOPE"), ("S3", "1")}))
        wires = list(compute_wires(p).values())
        assert [(w.source[0], w.target[0]) for w in wires] == [("S1", "S2"), ("S2", "S3")]
