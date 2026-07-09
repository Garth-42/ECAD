"""M8: end-to-end acceptance — the spec section 15 criteria, driven as tests."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from examples.motor_start_stop import build_project

from panelkit.cli import main
from panelkit.library.parts import PartLibrary
from panelkit.model.component import Component
from panelkit.model.geometry import Placement
from panelkit.model.project import Project
from panelkit.routing.resolve import resolve_wires
from panelkit.routing.router import route_wires, straight_line_length
from panelkit.rules.checks import clearance_violations, validate
from panelkit.views.bom import bom


class TestAcceptance:
    def test_validate_reports_zero_errors(self) -> None:
        findings = validate(build_project())
        assert [f for f in findings if f.severity == "error"] == []

    def test_bom_counts(self) -> None:
        rows = bom(build_project())
        counts = {r.part_number: r.quantity for r in rows}
        assert counts == {
            "1LE1003-0EB02": 1,
            "GV2ME14": 1,
            "LC1D09P7": 1,
            "LRD14": 1,
            "WDU2.5-8": 1,
            "XB4BA31": 1,
            "XB4BA42": 1,
        }

    def test_field_connections_star_through_x1(self) -> None:
        p = build_project()
        resolve_wires(p)
        field_wires = [w for w in p.wires.values() if w.net_id in ("n10", "n11", "n12")]
        assert len(field_wires) == 6
        assert all(w.target[0] == "X1" for w in field_wires)

    def test_every_wire_routed_and_duct_crossing_is_longer(self) -> None:
        p = build_project()
        resolve_wires(p)
        route_wires(p)
        assert all(w.length_mm is not None for w in p.wires.values())
        # The coil-return wire K1:A2 -> X1:7 must cross the panel via the
        # ducts; strictly longer than the straight line, even without slack.
        (coil_return,) = [w for w in p.wires.values() if w.net_id == "n23"]
        straight = straight_line_length(p, coil_return)
        run = coil_return.length_mm - max(50.0, 0.10 * (coil_return.length_mm / 1.10))
        assert coil_return.length_mm > straight
        path_len = sum(
            ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
            for a, b in zip(coil_return.path, coil_return.path[1:])
        )
        assert path_len > straight  # the routed centerline itself, before slack
        assert run > 0

    def test_clearance_silent_on_example_fires_on_crafted_fixture(self) -> None:
        assert clearance_violations(build_project()) == []
        # Separate fixture: same panel plus a deliberately-close neighbour.
        crowded = build_project()
        crowded.add_component(
            Component(
                tag="S3",
                part_number="XB4BA31",
                placement=Placement((485.0, 250.0, 0.0)),
                surface_id="plate",
            )
        )
        found = clearance_violations(crowded)
        assert found and any({"S1", "S3"} <= set(f.refs) for f in found)


class TestCliEndToEnd:
    def test_demo_writes_all_artifacts(self, tmp_path: Path, capsys) -> None:
        assert main(["demo", "-o", str(tmp_path)]) == 0
        project_json = tmp_path / "project.json"
        schematic = tmp_path / "schematic.svg"
        wiring = tmp_path / "wiring.svg"
        assert project_json.exists() and schematic.exists() and wiring.exists()
        data = json.loads(project_json.read_text())
        assert len(data["components"]) == 7
        assert all(w["length_mm"] is not None for w in data["wires"].values())
        for svg_file in (schematic, wiring):
            root = ET.fromstring(svg_file.read_text())
            assert root.tag.endswith("svg")

    def test_every_command_runs_clean_on_demo_output(self, tmp_path: Path, capsys) -> None:
        main(["demo", "-o", str(tmp_path)])
        capsys.readouterr()
        project = str(tmp_path / "project.json")

        assert main(["validate", project]) == 0
        assert "0 error(s)" in capsys.readouterr().out

        assert main(["bom", project]) == 0
        assert "GV2ME14" in capsys.readouterr().out

        assert main(["netlist", project]) == 0
        assert "CTRL_N" in capsys.readouterr().out

        assert main(["connections", project]) == 0
        assert "K1:A1" in capsys.readouterr().out

        assert main(["terminals", project]) == 0
        assert "[X1]" in capsys.readouterr().out

        assert main(["route", project]) == 0
        out = capsys.readouterr().out
        assert "CUT LIST" in out and "101" in out

        out_svg = tmp_path / "s2.svg"
        assert main(["render-schematic", project, "-o", str(out_svg)]) == 0
        assert ET.fromstring(out_svg.read_text()).tag.endswith("svg")
        capsys.readouterr()

        out_svg2 = tmp_path / "w2.svg"
        assert main(["render-wiring", project, "-o", str(out_svg2)]) == 0
        assert ET.fromstring(out_svg2.read_text()).tag.endswith("svg")

    def test_validate_exits_nonzero_on_bad_project(self, tmp_path: Path, capsys) -> None:
        p = Project(name="bad", library=PartLibrary.bundled())
        p.add_component(Component(tag="U1", part_number="GV2ME14", placement=Placement((0, 0, 0))))
        bad = tmp_path / "bad.json"
        from panelkit.persistence.json_store import save

        save(p, bad)
        # Sneak an unknown part number into the JSON to trigger an error.
        text = bad.read_text().replace("GV2ME14", "MISSING-9")
        bad.write_text(text)
        with pytest.raises(ValueError):
            main(["validate", str(bad)])  # load itself fails loudly


class TestSavedProjectRoundTrip:
    def test_demo_json_reloads_identically(self, tmp_path: Path, capsys) -> None:
        main(["demo", "-o", str(tmp_path)])
        from panelkit.persistence.json_store import load, save

        lib = PartLibrary.bundled()
        p1 = load(tmp_path / "project.json", lib)
        save(p1, tmp_path / "again.json")
        assert (tmp_path / "project.json").read_text() == (tmp_path / "again.json").read_text()
