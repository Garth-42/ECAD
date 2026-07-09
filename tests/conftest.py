"""Shared fixtures: a small two-button project used by persistence/rules tests."""

import pytest

from panelkit.library.parts import PartLibrary
from panelkit.model.component import Component
from panelkit.model.connectivity import Net
from panelkit.model.geometry import Placement
from panelkit.model.layout import Duct, MountingSurface
from panelkit.model.project import Project


@pytest.fixture()
def library() -> PartLibrary:
    return PartLibrary.bundled()


@pytest.fixture()
def small_project(library: PartLibrary) -> Project:
    """A minimal, fully-connected project: two buttons in series on a plate."""
    p = Project(name="small", library=library)
    p.add_surface(MountingSurface(id="plate", origin=(0.0, 0.0, 0.0), size=(300.0, 200.0)))
    p.add_component(
        Component(
            tag="S1",
            part_number="XB4BA42",
            placement=Placement((50.0, 50.0, 0.0)),
            surface_id="plate",
        )
    )
    p.add_component(
        Component(
            tag="S2",
            part_number="XB4BA31",
            placement=Placement((150.0, 50.0, 0.0), rotation_deg=180),
            surface_id="plate",
        )
    )
    p.add_net(Net(id="n_l", name="L", pins={("S1", "1")}, properties={"color": "red"}))
    p.add_net(Net(id="n_link", name="LINK", pins={("S1", "2"), ("S2", "3")}))
    p.add_net(Net(id="n_out", name="OUT", pins={("S2", "4")}))
    p.add_duct(Duct(id="d1", centerline=[(0.0, 100.0, 0.0), (300.0, 100.0, 0.0)], width_mm=40.0))
    return p
