"""Project aggregate root — the single source of truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator

from .component import Component, PinRef
from .connectivity import Net, Wire
from .harness import Bundle, Harness
from .layout import Duct, MountingSurface

if TYPE_CHECKING:
    from ..library.parts import Part, PartLibrary


@dataclass
class Project:
    name: str
    library: "PartLibrary"
    components: dict[str, Component] = field(default_factory=dict)
    nets: dict[str, Net] = field(default_factory=dict)
    wires: dict[str, Wire] = field(default_factory=dict)
    surfaces: dict[str, MountingSurface] = field(default_factory=dict)
    ducts: dict[str, Duct] = field(default_factory=dict)
    bundles: dict[str, Bundle] = field(default_factory=dict)
    harnesses: dict[str, Harness] = field(default_factory=dict)

    def add_component(self, component: Component) -> Component:
        if component.tag in self.components:
            raise ValueError(f"duplicate component tag {component.tag!r}")
        self.components[component.tag] = component
        return component

    def add_net(self, net: Net) -> Net:
        if net.id in self.nets:
            raise ValueError(f"duplicate net id {net.id!r}")
        self.nets[net.id] = net
        return net

    def add_surface(self, surface: MountingSurface) -> MountingSurface:
        if surface.id in self.surfaces:
            raise ValueError(f"duplicate surface id {surface.id!r}")
        self.surfaces[surface.id] = surface
        return surface

    def add_duct(self, duct: Duct) -> Duct:
        if duct.id in self.ducts:
            raise ValueError(f"duplicate duct id {duct.id!r}")
        self.ducts[duct.id] = duct
        return duct

    def net_of(self, pin_ref: PinRef) -> Net | None:
        for net_id in sorted(self.nets):
            if pin_ref in self.nets[net_id].pins:
                return self.nets[net_id]
        return None

    def part_of(self, component: Component) -> "Part":
        return self.library.get(component.part_number)

    def iter_components(self) -> Iterator[Component]:
        for tag in sorted(self.components):
            yield self.components[tag]

    def iter_nets(self) -> Iterator[Net]:
        for net_id in sorted(self.nets):
            yield self.nets[net_id]

    def iter_wires(self) -> Iterator[Wire]:
        for wire_id in sorted(self.wires):
            yield self.wires[wire_id]
