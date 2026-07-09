"""PanelKit domain model."""

from .component import Component, PinRef, world_pin_position
from .connectivity import Net, Wire, build_graph, cross_references, nets_from_graph
from .harness import Bundle, Harness, select_harness, select_harness_by_surface
from .geometry import (
    ALLOWED_ROTATIONS,
    BoundingBox,
    InvalidRotationError,
    Placement,
    aabb_gap,
    transform_point,
)
from .layout import Duct, MountingSurface
from .project import Project

__all__ = [
    "ALLOWED_ROTATIONS",
    "BoundingBox",
    "Bundle",
    "Component",
    "Duct",
    "Harness",
    "InvalidRotationError",
    "MountingSurface",
    "Net",
    "PinRef",
    "Placement",
    "Project",
    "Wire",
    "aabb_gap",
    "build_graph",
    "cross_references",
    "nets_from_graph",
    "select_harness",
    "select_harness_by_surface",
    "transform_point",
    "world_pin_position",
]
