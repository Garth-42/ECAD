"""Component instances and pin addressing.

A Component is an *instance* of a library Part placed in a project. Pins and
terminals are addressed by the tuple ``(component_tag, pin_name)`` — a PinRef.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .geometry import Placement, transform_point

if TYPE_CHECKING:
    from ..library.parts import PartLibrary

PinRef = tuple[str, str]


@dataclass
class Component:
    tag: str
    part_number: str
    placement: Placement
    surface_id: str | None = None

    def pin_refs(self, library: "PartLibrary") -> list[PinRef]:
        """All PinRefs of this component, in the part's pin order."""
        part = library.get(self.part_number)
        return [(self.tag, pin.name) for pin in part.pins]


def world_pin_position(component: Component, pin_name: str, library: "PartLibrary") -> np.ndarray:
    """World XYZ (length-3 ndarray) of a component pin."""
    part = library.get(component.part_number)
    for pin in part.pins:
        if pin.name == pin_name:
            return transform_point(pin.local_pos, component.placement)
    raise KeyError(
        f"pin {pin_name!r} not found on component {component.tag!r} "
        f"(part {component.part_number!r}; pins: {[p.name for p in part.pins]})"
    )
