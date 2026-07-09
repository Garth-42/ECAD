"""M10: WireViz export — mapping, document structure, golden file, runner."""

import shutil
from pathlib import Path

import pytest
import yaml

from examples.motor_start_stop import build_project_with_harness

from panelkit.cli import main
from panelkit.integrations.wireviz.export import export, to_wireviz_dict, to_yaml
from panelkit.integrations.wireviz.mapping import to_iec_color, to_wireviz_gauge
from panelkit.integrations.wireviz.runner import WirevizNotFoundError, render
from panelkit.model.harness import Bundle
from panelkit.routing.router import route_wires

GOLDEN = Path(__file__).parent / "data" / "motor_field_harness.golden.yml"


class TestMapping:
    @pytest.mark.parametrize(
        ("name", "code"),
        [
            ("black", "BK"),
            ("red", "RD"),
            ("blue", "BU"),
            ("grey", "GY"),
            ("gray", "GY"),
            ("purple", "VT"),
            ("BK", "BK"),  # already a code: pass through
            ("bn", "BN"),
        ],
    )
    def test_known_colors(self, name: str, code: str) -> None:
        assert to_iec_color(name) == (code, True)

    def test_unknown_color_passes_through(self) -> None:
        assert to_iec_color("chartreuse") == ("chartreuse", False)

    def test_gauge_pass_through(self) -> None:
        assert to_wireviz_gauge("1.5  mm2") == "1.5 mm2"
        assert to_wireviz_gauge("18 AWG") == "18 AWG"


class TestExportDocument:
    @pytest.fixture()
    def doc(self) -> dict:
        d, warnings = to_wireviz_dict(build_project_with_harness(), "H1")
        assert warnings == []
        return d

    def test_matches_golden_file(self, doc: dict) -> None:
        assert doc == yaml.safe_load(GOLDEN.read_text())

    def test_yaml_matches_golden_text(self) -> None:
        text, _ = to_yaml(build_project_with_harness(), "H1")
        assert text == GOLDEN.read_text()

    def test_terminal_block_is_a_connector_with_pins(self, doc: dict) -> None:
        x1 = doc["connectors"]["X1"]
        assert x1["pinlabels"] == [str(i) for i in range(1, 9)]
        assert x1["pn"] == "WDU2.5-8"

    def test_bundle_length_is_max_member_routed_length(self, doc: dict) -> None:
        p = build_project_with_harness()
        members = [p.wires[w] for w in p.bundles["W1"].wire_ids]
        expected = f"{round(max(w.length_mm for w in members), 1)} mm"
        assert doc["cables"]["W1"]["length"] == expected

    def test_colors_are_iec_codes(self, doc: dict) -> None:
        assert doc["cables"]["W1"]["colors"] == ["BK", "BK", "BK"]

    def test_w1_is_a_bundle_with_aligned_connection_set(self, doc: dict) -> None:
        assert doc["cables"]["W1"]["category"] == "bundle"
        assert doc["cables"]["W1"]["wirecount"] == 3
        (w1_set,) = [s for s in doc["connections"] if "W1" in s[1]]
        assert w1_set[0] == {"M1": ["U", "V", "W"]}
        assert w1_set[1] == {"W1": [1, 2, 3]}
        assert w1_set[2] == {"X1": ["1", "2", "3"]}

    def test_loose_wires_are_single_conductor_cables(self, doc: dict) -> None:
        loose = [k for k in doc["cables"] if k != "W1"]
        assert len(loose) == 3
        assert all(doc["cables"][k]["wirecount"] == 1 for k in loose)

    def test_wireviz_color_override_wins(self) -> None:
        p = build_project_with_harness()
        wid = p.bundles["W1"].wire_ids[0]
        p.wires[wid].wireviz_color = "BN"
        doc, warnings = to_wireviz_dict(p, "H1")
        assert doc["cables"]["W1"]["colors"][0] == "BN"
        assert warnings == []

    def test_unknown_color_warns_but_exports(self) -> None:
        p = build_project_with_harness()
        wid = p.bundles["W1"].wire_ids[0]
        p.wires[wid].wireviz_color = "chartreuse"
        doc, warnings = to_wireviz_dict(p, "H1")
        assert doc["cables"]["W1"]["colors"][0] == "chartreuse"
        assert [w.code for w in warnings] == ["wireviz_color"]

    def test_unrouted_wires_omit_length_with_warning(self) -> None:
        p = build_project_with_harness()
        for w in p.wires.values():
            w.length_mm = None
            w.path = None
        doc, warnings = to_wireviz_dict(p, "H1")
        assert all("length" not in c for c in doc["cables"].values())
        assert {w.code for w in warnings} == {"wireviz_length"}

    def test_unknown_harness_fails_loudly(self) -> None:
        with pytest.raises(ValueError, match="H9"):
            to_wireviz_dict(build_project_with_harness(), "H9")

    def test_non_point_to_point_bundle_fails_loudly(self) -> None:
        p = build_project_with_harness()
        route_wires(p)
        h = p.harnesses["H1"]
        p.bundles["W2"] = Bundle(id="W2", name="W2", wire_ids=sorted(h.wire_ids))
        h.bundle_ids.add("W2")
        with pytest.raises(ValueError, match="point-to-point"):
            to_wireviz_dict(p, "H1")

    def test_export_is_deterministic_and_pure(self, tmp_path: Path) -> None:
        p = build_project_with_harness()
        before = {k: (w.length_mm, w.color) for k, w in p.wires.items()}
        a, b = tmp_path / "a.yml", tmp_path / "b.yml"
        export(p, "H1", a)
        export(p, "H1", b)
        assert a.read_text() == b.read_text()
        assert {k: (w.length_mm, w.color) for k, w in p.wires.items()} == before


class TestCli:
    def test_harness_list(self, tmp_path: Path, capsys) -> None:
        main(["demo", "-o", str(tmp_path)])
        capsys.readouterr()
        assert main(["harness", "list", str(tmp_path / "project.json")]) == 0
        out = capsys.readouterr().out
        assert "H1" in out and "Motor feed" in out

    def test_export_wireviz_writes_golden_yaml(self, tmp_path: Path, capsys) -> None:
        main(["demo", "-o", str(tmp_path)])
        out_yml = tmp_path / "export.yml"
        assert (
            main(
                [
                    "export-wireviz",
                    str(tmp_path / "project.json"),
                    "--harness",
                    "H1",
                    "-o",
                    str(out_yml),
                ]
            )
            == 0
        )
        assert yaml.safe_load(out_yml.read_text()) == yaml.safe_load(GOLDEN.read_text())

    def test_demo_writes_harness_yaml(self, tmp_path: Path, capsys) -> None:
        assert main(["demo", "-o", str(tmp_path)]) == 0
        assert (tmp_path / "H1.yml").exists()


class TestRunner:
    def test_missing_cli_raises_actionable_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _: None)
        (tmp_path / "h.yml").write_text("{}")
        with pytest.raises(WirevizNotFoundError, match="panelkit\\[wireviz\\]"):
            render(tmp_path / "h.yml", tmp_path)

    @pytest.mark.skipif(shutil.which("wireviz") is None, reason="wireviz CLI not installed")
    def test_render_produces_drawing_and_bom(self, tmp_path: Path, capsys) -> None:
        main(["demo", "-o", str(tmp_path / "demo")])
        capsys.readouterr()
        rc = main(
            [
                "export-wireviz",
                str(tmp_path / "demo" / "project.json"),
                "--harness",
                "H1",
                "--render",
                "-o",
                str(tmp_path / "render"),
            ]
        )
        assert rc == 0
        produced = {p.name for p in (tmp_path / "render").iterdir()}
        assert "H1.yml" in produced
        assert "H1.svg" in produced
        assert any(name.endswith(".tsv") for name in produced)  # the BOM
