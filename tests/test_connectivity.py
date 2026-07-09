"""M1: net membership, graph building, cross-references."""

import networkx as nx

from panelkit.model.component import Component
from panelkit.model.connectivity import (
    Net,
    Wire,
    build_graph,
    cross_references,
    nets_from_graph,
)
from panelkit.model.geometry import Placement
from panelkit.model.project import Project


def make_project() -> Project:
    p = Project(name="t", library=None)  # type: ignore[arg-type]
    for tag in ("K1", "S1", "S2"):
        p.add_component(Component(tag=tag, part_number="X", placement=Placement((0, 0, 0))))
    p.add_net(Net(id="n1", name="START", pins={("S1", "14"), ("S2", "13"), ("K1", "A1")}))
    p.add_net(Net(id="n2", name="RET", pins={("K1", "A2"), ("S1", "1")}))
    return p


class TestNetMembership:
    def test_net_of(self) -> None:
        p = make_project()
        net = p.net_of(("K1", "A1"))
        assert net is not None and net.name == "START"
        assert p.net_of(("K1", "A2")).name == "RET"  # type: ignore[union-attr]

    def test_net_of_unknown_pin(self) -> None:
        assert make_project().net_of(("Z9", "1")) is None


class TestGraph:
    def test_components_match_nets(self) -> None:
        g = build_graph(make_project())
        comps = nets_from_graph(g)
        assert len(comps) == 2
        assert {("S1", "14"), ("S2", "13"), ("K1", "A1")} in comps
        assert {("K1", "A2"), ("S1", "1")} in comps

    def test_graph_uses_wires_when_resolved(self) -> None:
        p = make_project()
        p.wires["w1"] = Wire(
            id="w1", net_id="n1", source=("S1", "14"), target=("K1", "A1"), number="101"
        )
        g = build_graph(p)
        assert g.has_edge(("S1", "14"), ("K1", "A1"))
        assert g.edges[("S1", "14"), ("K1", "A1")]["wire_id"] == "w1"
        # Unwired pins still appear as nodes.
        assert ("S2", "13") in g.nodes

    def test_graph_is_networkx(self) -> None:
        assert isinstance(build_graph(make_project()), nx.Graph)


class TestCrossReferences:
    def test_returns_other_pins_sorted(self) -> None:
        p = make_project()
        assert cross_references(p, ("K1", "A1")) == [("S1", "14"), ("S2", "13")]

    def test_pin_without_net(self) -> None:
        assert cross_references(make_project(), ("Z9", "1")) == []
