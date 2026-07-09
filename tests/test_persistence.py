"""M3: JSON save/load round-trip.

NOTE: this file is not in the spec's illustrative tree, but M3 requires
round-trip tests and they deserve their own module.
"""

import json
from pathlib import Path

import pytest

from panelkit.library.parts import PartLibrary
from panelkit.model.connectivity import Wire
from panelkit.model.project import Project
from panelkit.persistence import load_project, save_project
from panelkit.persistence import sqlite_store
from panelkit.persistence.json_store import load, save


def test_round_trip_structural_equality(small_project: Project, tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save(small_project, path)
    loaded = load(path, small_project.library)

    assert loaded.name == small_project.name
    assert loaded.components == small_project.components
    assert loaded.nets == small_project.nets
    assert loaded.wires == small_project.wires
    assert loaded.surfaces == small_project.surfaces
    assert loaded.ducts == small_project.ducts


def test_round_trip_with_wires(small_project: Project, tmp_path: Path) -> None:
    small_project.wires["w1"] = Wire(
        id="w1",
        net_id="n_link",
        source=("S1", "2"),
        target=("S2", "3"),
        number="101",
        color="blue",
        length_mm=123.4,
        path=[(65.0, 55.0, 30.0), (65.0, 100.0, 0.0), (165.0, 100.0, 0.0)],
    )
    path = tmp_path / "p.json"
    save(small_project, path)
    loaded = load(path, small_project.library)
    assert loaded.wires == small_project.wires


def test_output_is_stable_and_sorted(small_project: Project, tmp_path: Path) -> None:
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    save(small_project, p1)
    save(small_project, p2)
    assert p1.read_text() == p2.read_text()
    data = json.loads(p1.read_text())
    keys = list(data.keys())
    assert keys == sorted(keys)
    # Library is never serialized; only part_number references are.
    assert "library" not in data
    assert data["components"]["S1"]["part_number"] == "XB4BA42"


def test_load_unknown_part_fails_loudly(small_project: Project, tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save(small_project, path)
    with pytest.raises(ValueError, match="unknown part"):
        load(path, PartLibrary())  # empty library


class TestSqliteBackend:
    """Stretch goal (spec section 11): same save/load interface over SQLite."""

    def _assert_equal(self, a: Project, b: Project) -> None:
        assert a.name == b.name
        assert a.components == b.components
        assert a.nets == b.nets
        assert a.wires == b.wires
        assert a.surfaces == b.surfaces
        assert a.ducts == b.ducts

    def test_round_trip(self, small_project: Project, tmp_path: Path) -> None:
        path = tmp_path / "p.db"
        sqlite_store.save(small_project, path)
        self._assert_equal(sqlite_store.load(path, small_project.library), small_project)

    def test_round_trip_with_routed_wires(self, small_project: Project, tmp_path: Path) -> None:
        small_project.wires["w1"] = Wire(
            id="w1",
            net_id="n_link",
            source=("S1", "2"),
            target=("S2", "3"),
            number="101",
            color="blue",
            length_mm=123.4,
            path=[(65.0, 55.0, 30.0), (65.0, 100.0, 0.0), (165.0, 100.0, 0.0)],
        )
        path = tmp_path / "p.sqlite"
        sqlite_store.save(small_project, path)
        loaded = sqlite_store.load(path, small_project.library)
        assert loaded.wires == small_project.wires

    def test_save_replaces_existing_file(self, small_project: Project, tmp_path: Path) -> None:
        path = tmp_path / "p.db"
        sqlite_store.save(small_project, path)
        sqlite_store.save(small_project, path)  # must not fail on existing schema
        self._assert_equal(sqlite_store.load(path, small_project.library), small_project)

    def test_unknown_part_fails_loudly(self, small_project: Project, tmp_path: Path) -> None:
        path = tmp_path / "p.db"
        sqlite_store.save(small_project, path)
        with pytest.raises(ValueError, match="unknown part"):
            sqlite_store.load(path, PartLibrary())

    def test_missing_file_fails_loudly(self, library: PartLibrary, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sqlite_store.load(tmp_path / "nope.db", library)


class TestExtensionDispatch:
    def test_json_and_sqlite_by_suffix(self, small_project: Project, tmp_path: Path) -> None:
        json_path = tmp_path / "p.json"
        db_path = tmp_path / "p.db"
        save_project(small_project, json_path)
        save_project(small_project, db_path)
        assert json_path.read_text().startswith("{")  # JSON backend
        assert db_path.read_bytes().startswith(b"SQLite format 3")  # SQLite backend
        for path in (json_path, db_path):
            loaded = load_project(path, small_project.library)
            assert loaded.components == small_project.components
            assert loaded.nets == small_project.nets
