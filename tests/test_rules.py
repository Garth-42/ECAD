"""M4: each rule fires on a crafted bad project and stays silent on a good one."""

from panelkit.library.parts import PartLibrary
from panelkit.model.component import Component
from panelkit.model.connectivity import Net
from panelkit.model.geometry import Placement
from panelkit.model.project import Project
from panelkit.rules.checks import (
    clearance_violations,
    duplicate_tags,
    empty_net,
    overcurrent,
    rotation_valid,
    unconnected_pins,
    unknown_part,
    validate,
)


def codes(findings) -> set[str]:
    return {f.code for f in findings}


class TestGoodProject:
    def test_clean_fixture_yields_no_errors(self, small_project: Project) -> None:
        findings = validate(small_project)
        assert not [f for f in findings if f.severity == "error"]
        # The single-pin nets in the fixture are warnings, by design.
        assert codes(findings) == {"empty_net"}


class TestDuplicateTags:
    def test_fires(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.components["S1"] = Component(
            tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))
        )
        p.components["S1b"] = Component(
            tag="S1", part_number="XB4BA31", placement=Placement((100, 0, 0))
        )
        found = duplicate_tags(p)
        assert len(found) == 1
        assert found[0].severity == "error"
        assert "S1" in found[0].message


class TestUnknownPart:
    def test_fires(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.add_component(Component(tag="U1", part_number="NOPE-1", placement=Placement((0, 0, 0))))
        found = unknown_part(p)
        assert len(found) == 1
        assert found[0].severity == "error"
        assert "NOPE-1" in found[0].message


class TestUnconnectedPins:
    def test_fires_per_dangling_pin(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))))
        p.add_net(Net(id="n1", name="L", pins={("S1", "1")}))
        found = unconnected_pins(p)
        assert [f.refs for f in found] == [("S1:2",)]
        assert found[0].severity == "warning"

    def test_silent_when_all_connected(self, small_project: Project) -> None:
        assert unconnected_pins(small_project) == []


class TestEmptyNet:
    def test_fires_on_small_nets(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.add_net(Net(id="n0", name="EMPTY", pins=set()))
        p.add_net(Net(id="n1", name="LONE", pins={("S1", "1")}))
        p.add_net(Net(id="n2", name="OK", pins={("S1", "1"), ("S2", "3")}))
        assert [f.refs for f in empty_net(p)] == [("n0",), ("n1",)]


class TestOvercurrent:
    def _project(self, library: PartLibrary, load: float | None) -> Project:
        p = Project(name="t", library=library)
        p.add_component(Component(tag="K1", part_number="LC1D09P7", placement=Placement((0, 0, 0))))
        p.add_component(
            Component(tag="Q1", part_number="GV2ME14", placement=Placement((100, 0, 0)))
        )
        props = {} if load is None else {"load_a": load}
        p.add_net(Net(id="n1", name="L1", pins={("Q1", "T1"), ("K1", "1")}, properties=props))
        return p

    def test_fires_above_lowest_rating(self, library: PartLibrary) -> None:
        found = overcurrent(self._project(library, load=9.5))  # K1 rated 9 A
        assert len(found) == 1
        assert found[0].severity == "warning"
        assert "K1" in found[0].message

    def test_silent_at_or_below_rating(self, library: PartLibrary) -> None:
        assert overcurrent(self._project(library, load=8.0)) == []

    def test_skipped_when_no_load_declared(self, library: PartLibrary) -> None:
        assert overcurrent(self._project(library, load=None)) == []


class TestRotationValid:
    def test_fires_on_smuggled_rotation(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        placement = Placement((0, 0, 0))
        object.__setattr__(placement, "rotation_deg", 45)  # bypass __post_init__
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=placement))
        found = rotation_valid(p)
        assert len(found) == 1
        assert found[0].severity == "error"
        assert "45" in found[0].message

    def test_silent_on_valid_rotations(self, small_project: Project) -> None:
        assert rotation_valid(small_project) == []


class TestClearance:
    def test_fires_on_too_close_pair(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        # Two 30 mm buttons 5 mm apart: violates the 10 mm minimum gap.
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))))
        p.add_component(Component(tag="S2", part_number="XB4BA31", placement=Placement((35, 0, 0))))
        found = clearance_violations(p, min_gap_mm=10.0)
        assert len(found) == 1
        assert found[0].refs == ("S1", "S2")

    def test_fires_on_overlap(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))))
        p.add_component(Component(tag="S2", part_number="XB4BA31", placement=Placement((10, 0, 0))))
        found = clearance_violations(p)
        assert len(found) == 1
        assert "overlaps" in found[0].message

    def test_silent_on_clean_layout(self, small_project: Project) -> None:
        assert clearance_violations(small_project) == []


class TestValidateOrdering:
    def test_errors_sort_before_warnings(self, library: PartLibrary) -> None:
        p = Project(name="bad", library=library)
        p.add_component(Component(tag="U1", part_number="NOPE-1", placement=Placement((0, 0, 0))))
        p.add_net(Net(id="n0", name="EMPTY", pins=set()))
        findings = validate(p)
        severities = [f.severity for f in findings]
        assert severities == sorted(severities, key={"error": 0, "warning": 1}.get)
        assert findings[0].code == "unknown_part"
