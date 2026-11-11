"""Resolve nets into discrete two-point wires.

A net with N pins is not one wire. Deterministic conversion rules:

- Net contains a terminal_block pin -> star: every other pin wires to the
  terminal (the real-world norm).
- Exactly two pins -> one wire.
- Otherwise -> daisy-chain the pins nearest-neighbour by world position,
  starting from the first pin in sorted order (ties break in sorted order),
  so the chain follows the layout instead of the alphabet. Pins that cannot
  be located fall back to plain sorted order.

Wire numbers are a global incrementing integer (starting at 101) assigned in
sorted-net order, so numbering is reproducible across runs.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np

from ..model.component import PinRef, world_pin_position
from ..model.connectivity import Net, Wire
from ..model.project import Project

FIRST_WIRE_NUMBER = 101


def _is_terminal_pin(project: Project, pin: PinRef) -> bool:
    component = project.components.get(pin[0])
    if component is None:
        raise ValueError(f"net pin {pin[0]}:{pin[1]} references unknown component {pin[0]!r}")
    return project.part_of(component).category == "terminal_block"


def _chain_order(project: Project, pins: list[PinRef]) -> list[PinRef]:
    """Greedy nearest-neighbour ordering of ``pins`` (already sorted)."""
    try:
        pos = {p: world_pin_position(project.components[p[0]], p[1], project.library) for p in pins}
    except KeyError:  # unknown part or pin: validation reports it; stay deterministic
        return pins
    ordered = [pins[0]]
    remaining = pins[1:]
    while remaining:
        here = pos[ordered[-1]]
        # Rounding keeps float noise from reordering equidistant pins.
        nearest = min(remaining, key=lambda p: (round(float(np.linalg.norm(pos[p] - here)), 6), p))
        remaining.remove(nearest)
        ordered.append(nearest)
    return ordered


def _net_pairs(project: Project, net: Net) -> list[tuple[PinRef, PinRef]]:
    """Source/target pairs for one net, in deterministic order."""
    pins = sorted(net.pins)
    if len(pins) < 2:
        return []
    terminals = [p for p in pins if _is_terminal_pin(project, p)]
    if terminals:
        hub = terminals[0]
        return [(p, hub) for p in pins if p != hub]
    if len(pins) == 2:
        return [(pins[0], pins[1])]
    return list(pairwise(_chain_order(project, pins)))


def compute_wires(project: Project) -> dict[str, Wire]:
    """Pure computation of the resolved wires; does not touch the model."""
    wires: dict[str, Wire] = {}
    number = FIRST_WIRE_NUMBER
    for net in project.iter_nets():
        gauge = net.properties.get("gauge", "1.0 mm2")
        color = net.properties.get("color", "black")
        for source, target in _net_pairs(project, net):
            wire = Wire(
                id=f"w{number}",
                net_id=net.id,
                source=source,
                target=target,
                number=str(number),
                gauge=gauge,
                color=color,
            )
            wires[wire.id] = wire
            number += 1
    return wires


def resolve_wires(project: Project) -> dict[str, Wire]:
    """Populate ``project.wires`` (one of the two sanctioned model writers)."""
    project.wires = compute_wires(project)
    return project.wires
