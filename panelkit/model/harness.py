"""Harness-level grouping: bundles of wires and exportable harness subsets.

A ``Bundle`` groups existing wires that physically travel together between two
components (v1 bundles are point-to-point). A ``Harness`` names a build-level
subset of the panel — the unit WireViz documents. Selection helpers are pure:
they return a ``Harness`` and mutate nothing; registering one on the project
is an explicit ``project.harnesses[h.id] = h``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .project import Project


@dataclass
class Bundle:
    id: str
    name: str  # WireViz cable designator, e.g. "W1"
    wire_ids: list[str]  # existing Wire ids that run together
    kind: str = "bundle"  # "bundle" (loose) | "cable" (jacketed)
    color_code: str | None = None  # optional WireViz auto scheme, e.g. "DIN"
    pn: str | None = None
    manufacturer: str | None = None
    mpn: str | None = None


@dataclass
class Harness:
    id: str
    name: str
    component_tags: set[str]  # connectors to include (incl. terminals)
    wire_ids: set[str]  # all wires in this harness
    bundle_ids: set[str] = field(default_factory=set)


def select_harness(
    project: "Project", component_tags: set[str], name: str, harness_id: str | None = None
) -> Harness:
    """Harness of every wire whose *both* endpoints lie on ``component_tags``.

    Bundles all of whose wires fall in that set are included too.
    """
    unknown = sorted(t for t in component_tags if t not in project.components)
    if unknown:
        raise ValueError(f"harness selection references unknown components: {unknown}")
    wire_ids = {
        w.id
        for w in project.wires.values()
        if w.source[0] in component_tags and w.target[0] in component_tags
    }
    bundle_ids = {
        b.id for b in project.bundles.values() if b.wire_ids and set(b.wire_ids) <= wire_ids
    }
    return Harness(
        id=harness_id if harness_id is not None else name,
        name=name,
        component_tags=set(component_tags),
        wire_ids=wire_ids,
        bundle_ids=bundle_ids,
    )


def select_harness_by_surface(
    project: "Project", surface_id: str, name: str, harness_id: str | None = None
) -> Harness:
    """Harness of wires crossing into/out of one mounting surface.

    A wire "crosses" when exactly one endpoint sits on a component mounted on
    ``surface_id`` — the field-harness case. Included components are all the
    endpoints those wires touch.
    """
    if surface_id not in project.surfaces:
        raise ValueError(f"unknown surface {surface_id!r}")

    def on_surface(tag: str) -> bool:
        component = project.components.get(tag)
        if component is None:
            raise ValueError(f"wire endpoint references unknown component {tag!r}")
        return component.surface_id == surface_id

    wire_ids: set[str] = set()
    tags: set[str] = set()
    for w in project.wires.values():
        if on_surface(w.source[0]) != on_surface(w.target[0]):
            wire_ids.add(w.id)
            tags.add(w.source[0])
            tags.add(w.target[0])
    bundle_ids = {
        b.id for b in project.bundles.values() if b.wire_ids and set(b.wire_ids) <= wire_ids
    }
    return Harness(
        id=harness_id if harness_id is not None else name,
        name=name,
        component_tags=tags,
        wire_ids=wire_ids,
        bundle_ids=bundle_ids,
    )
