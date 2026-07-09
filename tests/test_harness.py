"""M9: bundles, harness selection, persistence round-trip, back-compat."""

import json
from pathlib import Path

import pytest

from examples.motor_start_stop import build_project, build_project_with_harness

from panelkit.model.component import Component
from panelkit.model.geometry import Placement
from panelkit.model.harness import Bundle, select_harness, select_harness_by_surface
from panelkit.model.layout import MountingSurface
from panelkit.model.project import Project
from panelkit.persistence import json_store, sqlite_store
from panelkit.routing.resolve import resolve_wires


class TestSelectHarness:
    def test_picks_wires_with_both_endpoints_inside(self) -> None:
        p = build_project()
        resolve_wires(p)
        h = select_harness(p, {"X1", "F1", "M1"}, name="Motor feed", harness_id="H1")
        assert h.id == "H1" and h.name == "Motor feed"
        assert len(h.wire_ids) == 6  # 3x F1->X1 + 3x M1->X1 stars
        for wid in h.wire_ids:
            w = p.wires[wid]
            assert {w.source[0], w.target[0]} <= {"X1", "F1", "M1"}

    def test_excludes_wires_leaving_the_set(self) -> None:
        p = build_project()
        resolve_wires(p)
        h = select_harness(p, {"X1"}, name="just the strip")
        assert h.wire_ids == set()  # every X1 wire has its far end elsewhere

    def test_selection_is_pure(self) -> None:
        p = build_project()
        resolve_wires(p)
        select_harness(p, {"X1", "F1", "M1"}, name="n")
        assert p.harnesses == {}

    def test_includes_fully_contained_bundles_only(self) -> None:
        p = build_project()
        resolve_wires(p)
        motor = sorted(w.id for w in p.wires.values() if {w.source[0], w.target[0]} == {"M1", "X1"})
        p.bundles["W1"] = Bundle(id="W1", name="W1", wire_ids=motor)
        stray = next(w.id for w in p.wires.values() if w.source[0] == "Q1")
        p.bundles["W2"] = Bundle(id="W2", name="W2", wire_ids=[*motor[:1], stray])
        h = select_harness(p, {"X1", "F1", "M1"}, name="Motor feed")
        assert h.bundle_ids == {"W1"}  # W2 has a wire outside the harness

    def test_unknown_tag_fails_loudly(self) -> None:
        p = build_project()
        with pytest.raises(ValueError, match="Z9"):
            select_harness(p, {"X1", "Z9"}, name="bad")


class TestSelectHarnessBySurface:
    def _project_with_field_surface(self) -> Project:
        p = build_project()
        # A separate "field" surface holding the motor: its supply wires cross.
        p.add_surface(MountingSurface(id="field", origin=(700.0, 0.0, 0.0), size=(200.0, 200.0)))
        p.components["M1"].surface_id = "field"
        resolve_wires(p)
        return p

    def test_crossing_wires_selected(self) -> None:
        p = self._project_with_field_surface()
        h = select_harness_by_surface(p, "field", name="Field harness")
        assert len(h.wire_ids) == 3  # M1 U/V/W to X1
        assert h.component_tags == {"M1", "X1"}

    def test_unknown_surface_fails_loudly(self) -> None:
        p = build_project()
        with pytest.raises(ValueError, match="nope"):
            select_harness_by_surface(p, "nope", name="bad")


class TestCanonicalHarness:
    def test_example_defines_h1_with_w1(self) -> None:
        p = build_project_with_harness()
        assert set(p.harnesses) == {"H1"}
        h = p.harnesses["H1"]
        assert h.component_tags == {"X1", "F1", "M1"}
        assert len(h.wire_ids) == 6
        assert h.bundle_ids == {"W1"}
        w1 = p.bundles["W1"]
        assert len(w1.wire_ids) == 3
        assert all(p.wires[wid].length_mm is not None for wid in h.wire_ids)  # routed


class TestPersistence:
    def test_json_round_trip_with_harness(self, tmp_path: Path) -> None:
        p = build_project_with_harness()
        p.wires[next(iter(p.bundles["W1"].wire_ids))].wireviz_color = "BN"
        path = tmp_path / "p.json"
        json_store.save(p, path)
        loaded = json_store.load(path, p.library)
        assert loaded.bundles == p.bundles
        assert loaded.harnesses == p.harnesses
        assert loaded.wires == p.wires

    def test_sqlite_round_trip_with_harness(self, tmp_path: Path) -> None:
        p = build_project_with_harness()
        path = tmp_path / "p.db"
        sqlite_store.save(p, path)
        loaded = sqlite_store.load(path, p.library)
        assert loaded.bundles == p.bundles
        assert loaded.harnesses == p.harnesses
        assert loaded.wires == p.wires

    def test_pre_m9_json_file_still_loads(self, tmp_path: Path, library) -> None:
        """A file written before M9 has no bundles/harnesses/wireviz_color keys."""
        p = Project(name="old", library=library)
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))))
        path = tmp_path / "old.json"
        json_store.save(p, path)
        data = json.loads(path.read_text())
        del data["bundles"], data["harnesses"]
        data["format_version"] = 1
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        loaded = json_store.load(path, library)
        assert loaded.bundles == {} and loaded.harnesses == {}

    def test_pre_m9_wire_without_wireviz_color_loads(self, tmp_path: Path, library) -> None:
        p = build_project(library)
        resolve_wires(p)
        path = tmp_path / "old.json"
        json_store.save(p, path)
        data = json.loads(path.read_text())
        for w in data["wires"].values():
            del w["wireviz_color"]
        data["format_version"] = 1
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        loaded = json_store.load(path, library)
        assert all(w.wireviz_color is None for w in loaded.wires.values())

    def test_pre_m9_sqlite_file_still_loads(self, tmp_path: Path, library) -> None:
        """Simulate a version-1 database: no wireviz_color column, no new tables."""
        p = build_project(library)
        resolve_wires(p)
        path = tmp_path / "old.db"
        sqlite_store.save(p, path)
        import sqlite3

        con = sqlite3.connect(path)
        con.executescript(
            "ALTER TABLE wires DROP COLUMN wireviz_color;"
            "DROP TABLE bundles; DROP TABLE harnesses;"
            "UPDATE meta SET value = '1' WHERE key = 'format_version';"
        )
        con.commit()
        con.close()
        loaded = sqlite_store.load(path, library)
        assert loaded.bundles == {} and loaded.harnesses == {}
        assert all(w.wireviz_color is None for w in loaded.wires.values())
        assert len(loaded.wires) == len(p.wires)
