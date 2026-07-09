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
