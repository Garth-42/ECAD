"""Canonical example: three-phase motor start/stop panel (spec section 12).

Control logic (seal-in / latching):
    line -> S1 stop (NC) -> S2 start (NO) -> K1 coil A1; the K1 aux contact
    13-14 parallels S2 to seal in; K1 coil A2 returns to neutral.
Power:
    Q1 breaker -> K1 main poles -> F1 overload -> M1 motor (U/V/W),
    with the motor and incoming field connections landed on terminal strip X1
    so resolve() produces stars through the terminal block.
"""

from __future__ import annotations

from ..library.parts import PartLibrary
from ..model.component import Component
from ..model.connectivity import Net
from ..model.geometry import Placement
from ..model.layout import Duct, MountingSurface
from ..model.project import Project

MOTOR_LOAD_A = 4.9

_POWER = {"gauge": "1.5 mm2", "color": "black", "load_a": MOTOR_LOAD_A}
_CTRL = {"gauge": "0.75 mm2", "color": "red"}
_NEUTRAL = {"gauge": "0.75 mm2", "color": "blue"}


def build_project(library: PartLibrary | None = None) -> Project:
    """Build the motor start/stop project used as the acceptance fixture."""
    lib = library if library is not None else PartLibrary.bundled()
    p = Project(name="motor_start_stop", library=lib)

    p.add_surface(MountingSurface(id="plate", origin=(0.0, 0.0, 0.0), size=(600.0, 600.0)))

    def place(tag: str, part: str, x: float, y: float, rot: int = 0) -> None:
        p.add_component(
            Component(
                tag=tag,
                part_number=part,
                placement=Placement((x, y, 0.0), rotation_deg=rot),
                surface_id="plate",
            )
        )

    place("Q1", "GV2ME14", 60.0, 450.0)
    place("K1", "LC1D09P7", 160.0, 450.0)
    place("F1", "LRD14", 260.0, 450.0)
    place("S1", "XB4BA42", 450.0, 250.0)
    place("S2", "XB4BA31", 520.0, 250.0)
    place("X1", "WDU2.5-8", 100.0, 100.0, rot=90)
    place("M1", "1LE1003-0EB02", 420.0, 90.0)

    def net(net_id: str, name: str, pins: set[tuple[str, str]], props: dict) -> None:
        p.add_net(Net(id=net_id, name=name, pins=pins, properties=dict(props)))

    # Incoming supply lands on X1, then feeds the breaker.
    net("n01", "L1", {("X1", "4"), ("Q1", "L1")}, _POWER)
    net("n02", "L2", {("X1", "5"), ("Q1", "L2")}, _POWER)
    net("n03", "L3", {("X1", "6"), ("Q1", "L3")}, _POWER)
    # Breaker -> contactor mains.
    net("n04", "L1A", {("Q1", "T1"), ("K1", "1")}, _POWER)
    net("n05", "L2A", {("Q1", "T2"), ("K1", "3")}, _POWER)
    net("n06", "L3A", {("Q1", "T3"), ("K1", "5")}, _POWER)
    # Contactor -> overload.
    net("n07", "L1B", {("K1", "2"), ("F1", "1")}, _POWER)
    net("n08", "L2B", {("K1", "4"), ("F1", "3")}, _POWER)
    net("n09", "L3B", {("K1", "6"), ("F1", "5")}, _POWER)
    # Overload -> motor, starred through the terminal strip (field wiring).
    net("n10", "T1", {("F1", "2"), ("X1", "1"), ("M1", "U")}, _POWER)
    net("n11", "T2", {("F1", "4"), ("X1", "2"), ("M1", "V")}, _POWER)
    net("n12", "T3", {("F1", "6"), ("X1", "3"), ("M1", "W")}, _POWER)
    # Control circuit: line -> stop -> start -> coil, aux 13-14 seals in.
    net("n20", "CTRL_L", {("X1", "8"), ("S1", "1")}, _CTRL)
    net("n21", "START", {("S1", "2"), ("S2", "3"), ("K1", "13")}, _CTRL)
    net("n22", "COIL", {("S2", "4"), ("K1", "14"), ("K1", "A1")}, _CTRL)
    net("n23", "CTRL_N", {("K1", "A2"), ("X1", "7")}, _NEUTRAL)

    # Wireway: a top run under the power row, a drop, and a bottom run,
    # meeting at shared waypoints so the duct graph is connected.
    p.add_duct(
        Duct(
            id="d_top",
            centerline=[(20.0, 420.0, 0.0), (300.0, 420.0, 0.0), (580.0, 420.0, 0.0)],
        )
    )
    p.add_duct(
        Duct(
            id="d_drop",
            centerline=[(300.0, 420.0, 0.0), (300.0, 240.0, 0.0), (300.0, 60.0, 0.0)],
        )
    )
    p.add_duct(
        Duct(
            id="d_bot",
            centerline=[(20.0, 60.0, 0.0), (300.0, 60.0, 0.0), (580.0, 60.0, 0.0)],
        )
    )
    return p
