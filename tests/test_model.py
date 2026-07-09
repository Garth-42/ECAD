"""M1/M2: component pins, project aggregate, parts library."""

import json
from pathlib import Path

import numpy as np
import pytest

from panelkit.library.parts import Part, PartLibrary, UnknownPartError
from panelkit.model.component import Component, world_pin_position
from panelkit.model.connectivity import Net
from panelkit.model.geometry import Placement
from panelkit.model.project import Project


class TestPartLibrary:
    def test_bundled_parts_load(self) -> None:
        lib = PartLibrary.bundled()
        assert len(lib) >= 7
        part = lib.get("LC1D09P7")
        assert part.category == "contactor"
        assert {p.name for p in part.pins} >= {"A1", "A2", "13", "14", "1", "2"}

    def test_unknown_part_raises(self) -> None:
        with pytest.raises(UnknownPartError, match="NOPE-123"):
            PartLibrary.bundled().get("NOPE-123")

    def test_load_directory(self, tmp_path: Path) -> None:
        (tmp_path / "widget.json").write_text(
            json.dumps(
                {
                    "part_number": "W1",
                    "manufacturer": "ACME",
                    "description": "widget",
                    "category": "other",
                    "pins": [{"name": "P1", "local_pos": [1.0, 2.0, 3.0]}],
                    "size": [10.0, 10.0, 10.0],
                }
            )
        )
        lib = PartLibrary()
        lib.load_directory(tmp_path)
        assert lib.get("W1").pins[0].local_pos == (1.0, 2.0, 3.0)

    def test_bad_category_rejected(self) -> None:
        with pytest.raises(ValueError, match="category"):
            Part(
                part_number="B1",
                manufacturer="ACME",
                description="bad",
                category="flux_capacitor",
                pins=(),
                size=(1.0, 1.0, 1.0),
            )

    def test_missing_field_raises_with_filename(self, tmp_path: Path) -> None:
        (tmp_path / "broken.json").write_text(json.dumps({"part_number": "B2"}))
        lib = PartLibrary()
        with pytest.raises(ValueError, match="broken.json"):
            lib.load_directory(tmp_path)


class TestComponent:
    def test_pin_refs(self) -> None:
        lib = PartLibrary.bundled()
        c = Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0)))
        assert c.pin_refs(lib) == [("S1", "1"), ("S1", "2")]

    def test_world_pin_position_translated(self) -> None:
        lib = PartLibrary.bundled()
        c = Component(tag="S1", part_number="XB4BA42", placement=Placement((100.0, 200.0, 0.0)))
        assert np.allclose(world_pin_position(c, "1", lib), [115.0, 225.0, 30.0])

    def test_world_pin_position_rotated(self) -> None:
        lib = PartLibrary.bundled()
        c = Component(
            tag="X1",
            part_number="WDU2.5-8",
            placement=Placement((100.0, 100.0, 0.0), rotation_deg=90),
        )
        # local (5, 5, 40) -> rotated (-5, 5, 40) -> world (95, 105, 40)
        assert np.allclose(world_pin_position(c, "1", lib), [95.0, 105.0, 40.0])

    def test_unknown_pin_raises(self) -> None:
        lib = PartLibrary.bundled()
        c = Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0)))
        with pytest.raises(KeyError, match="Z9"):
            world_pin_position(c, "Z9", lib)


class TestProject:
    def test_duplicate_tag_rejected(self) -> None:
        p = Project(name="t", library=PartLibrary.bundled())
        c = Component(tag="K1", part_number="LC1D09P7", placement=Placement((0, 0, 0)))
        p.add_component(c)
        with pytest.raises(ValueError, match="K1"):
            p.add_component(c)

    def test_part_of(self) -> None:
        p = Project(name="t", library=PartLibrary.bundled())
        c = p.add_component(
            Component(tag="M1", part_number="1LE1003-0EB02", placement=Placement((0, 0, 0)))
        )
        assert p.part_of(c).category == "motor"

    def test_duplicate_net_rejected(self) -> None:
        p = Project(name="t", library=PartLibrary.bundled())
        p.add_net(Net(id="n1", name="A"))
        with pytest.raises(ValueError, match="n1"):
            p.add_net(Net(id="n1", name="B"))
