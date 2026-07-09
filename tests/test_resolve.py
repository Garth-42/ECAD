"""M5: nets -> wires (star through terminals, pairs, daisy chains, numbering)."""

from examples.motor_start_stop import build_project

from panelkit.library.parts import PartLibrary
from panelkit.model.component import Component
from panelkit.model.connectivity import Net
from panelkit.model.geometry import Placement
from panelkit.model.project import Project
from panelkit.routing.resolve import compute_wires, resolve_wires


def wires_of_net(wires: dict, net_id: str) -> list:
    return [w for w in wires.values() if w.net_id == net_id]


class TestTopologies:
    def test_two_pin_net_is_one_wire(self, library: PartLibrary) -> None:
        p = Project(name="t", library=library)
        p.add_component(Component(tag="S1", part_number="XB4BA42", placement=Placement((0, 0, 0))))
        p.add_component(
            Component(tag="S2", part_number="XB4BA31", placement=Placement((100, 0, 0)))
        )
        p.add_net(Net(id="n1", name="A", pins={("S1", "2"), ("S2", "3")}))
        wires = compute_wires(p)
        assert len(wires) == 1
        (w,) = wires.values()
        assert (w.source, w.target) == (("S1", "2"), ("S2", "3"))

    def test_terminal_net_stars_through_terminal(self, library: PartLibrary) -> None:
        p = Project(name="t", library=library)
        p.add_component(Component(tag="X1", part_number="WDU2.5-8", placement=Placement((0, 0, 0))))
        p.add_component(Component(tag="F1", part_number="LRD14", placement=Placement((100, 0, 0))))
        p.add_component(
            Component(tag="M1", part_number="1LE1003-0EB02", placement=Placement((300, 0, 0)))
        )
        p.add_net(Net(id="n1", name="T1", pins={("F1", "2"), ("X1", "1"), ("M1", "U")}))
        wires = compute_wires(p)
        assert len(wires) == 2
        for w in wires.values():
            assert w.target == ("X1", "1")  # every wire lands on the terminal
        assert {w.source for w in wires.values()} == {("F1", "2"), ("M1", "U")}

    def test_multi_pin_net_daisy_chains_sorted(self, library: PartLibrary) -> None:
        p = Project(name="t", library=library)
        p.add_component(Component(tag="K1", part_number="LC1D09P7", placement=Placement((0, 0, 0))))
        p.add_component(
            Component(tag="S1", part_number="XB4BA42", placement=Placement((100, 0, 0)))
        )
        p.add_component(
            Component(tag="S2", part_number="XB4BA31", placement=Placement((200, 0, 0)))
        )
        p.add_net(Net(id="n1", name="START", pins={("S1", "2"), ("S2", "3"), ("K1", "13")}))
        wires = sorted(compute_wires(p).values(), key=lambda w: w.number)
        assert [(w.source, w.target) for w in wires] == [
            (("K1", "13"), ("S1", "2")),
            (("S1", "2"), ("S2", "3")),
        ]

    def test_unknown_component_in_net_fails_loudly(self, library: PartLibrary) -> None:
        p = Project(name="t", library=library)
        p.add_net(Net(id="n1", name="A", pins={("Z9", "1"), ("Z9", "2")}))
        try:
            compute_wires(p)
        except ValueError as exc:
            assert "Z9" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestDeterminism:
    def test_numbering_stable_across_runs(self) -> None:
        w1 = compute_wires(build_project())
        w2 = compute_wires(build_project())
        assert {k: (v.number, v.source, v.target) for k, v in w1.items()} == {
            k: (v.number, v.source, v.target) for k, v in w2.items()
        }

    def test_properties_carried_from_net(self) -> None:
        p = build_project()
        wires = compute_wires(p)
        coil = wires_of_net(wires, "n22")
        assert all(w.color == "red" and w.gauge == "0.75 mm2" for w in coil)


class TestCanonicalExample:
    def test_wire_count(self) -> None:
        p = build_project()
        resolve_wires(p)
        # 9 two-pin power nets + 3 motor stars (2 each) + control (1+2+2+1)
        assert len(p.wires) == 21

    def test_resolve_populates_model(self) -> None:
        p = build_project()
        assert p.wires == {}
        resolve_wires(p)
        assert p.wires and all(w.length_mm is None for w in p.wires.values())

    def test_field_nets_star_through_x1(self) -> None:
        p = build_project()
        resolve_wires(p)
        for net_id in ("n10", "n11", "n12"):
            for w in wires_of_net(p.wires, net_id):
                assert w.target[0] == "X1"
