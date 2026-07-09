"""Validation rules ("online checks").

Each rule is a pure function ``(project) -> list[Finding]``. Rules read the
model and return data; they never mutate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
from scipy.spatial import cKDTree

from ..library.parts import UnknownPartError
from ..model.geometry import ALLOWED_ROTATIONS, BoundingBox, aabb_gap
from ..model.project import Project

Severity = str  # "error" | "warning"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    refs: tuple[str, ...] = field(default_factory=tuple)


def duplicate_tags(project: Project) -> list[Finding]:
    """Two components share a tag.

    The dict-keyed model makes true duplicates unrepresentable, but a
    component whose ``tag`` field disagrees with its dict key counts too.
    """
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for key in sorted(project.components):
        tag = project.components[key].tag
        if tag in seen:
            findings.append(
                Finding(
                    severity="error",
                    code="duplicate_tags",
                    message=f"components {seen[tag]!r} and {key!r} share tag {tag!r}",
                    refs=(seen[tag], key),
                )
            )
        else:
            seen[tag] = key
    return findings


def unknown_part(project: Project) -> list[Finding]:
    findings = []
    for c in project.iter_components():
        try:
            project.library.get(c.part_number)
        except UnknownPartError:
            findings.append(
                Finding(
                    severity="error",
                    code="unknown_part",
                    message=f"component {c.tag!r}: part number {c.part_number!r} not in library",
                    refs=(c.tag,),
                )
            )
    return findings


def unconnected_pins(project: Project) -> list[Finding]:
    connected: set[tuple[str, str]] = set()
    for net in project.nets.values():
        connected |= net.pins
    findings = []
    for c in project.iter_components():
        if c.part_number not in project.library:
            continue  # unknown_part reports this
        for ref in c.pin_refs(project.library):
            if ref not in connected:
                findings.append(
                    Finding(
                        severity="warning",
                        code="unconnected_pins",
                        message=f"pin {ref[0]}:{ref[1]} belongs to no net",
                        refs=(f"{ref[0]}:{ref[1]}",),
                    )
                )
    return findings


def empty_net(project: Project) -> list[Finding]:
    return [
        Finding(
            severity="warning",
            code="empty_net",
            message=f"net {net.id!r} ({net.name!r}) has fewer than two pins",
            refs=(net.id,),
        )
        for net in project.iter_nets()
        if len(net.pins) < 2
    ]


def overcurrent(project: Project) -> list[Finding]:
    """Net load exceeds the lowest current rating among its components."""
    findings = []
    for net in project.iter_nets():
        load = net.properties.get("load_a")
        if load is None:
            continue
        ratings = []
        for tag in sorted({t for t, _ in net.pins}):
            component = project.components.get(tag)
            if component is None or component.part_number not in project.library:
                continue
            rating = project.library.get(component.part_number).current_rating_a
            if rating is not None:
                ratings.append((rating, tag))
        if not ratings:
            continue
        min_rating, weakest = min(ratings)
        if load > min_rating:
            findings.append(
                Finding(
                    severity="warning",
                    code="overcurrent",
                    message=(
                        f"net {net.id!r} ({net.name!r}): load {load} A exceeds "
                        f"lowest rating {min_rating} A ({weakest})"
                    ),
                    refs=(net.id, weakest),
                )
            )
    return findings


def rotation_valid(project: Project) -> list[Finding]:
    return [
        Finding(
            severity="error",
            code="rotation_valid",
            message=(
                f"component {c.tag!r}: rotation {c.placement.rotation_deg} "
                f"not in {sorted(ALLOWED_ROTATIONS)}"
            ),
            refs=(c.tag,),
        )
        for c in project.iter_components()
        if c.placement.rotation_deg not in ALLOWED_ROTATIONS
    ]


def clearance_violations(project: Project, min_gap_mm: float = 10.0) -> list[Finding]:
    """Component AABBs that overlap or sit closer than ``min_gap_mm``.

    A KDTree over AABB centroids prunes candidate pairs; the exact
    axis-aligned gap decides each candidate.
    """
    tagged = [c for c in project.iter_components() if c.part_number in project.library]
    boxes = []
    for c in tagged:
        part = project.library.get(c.part_number)
        boxes.append(BoundingBox(part.size).world_aabb(c.placement))
    if len(tagged) < 2:
        return []

    centroids = np.array([(lo + hi) / 2.0 for lo, hi in boxes])
    # Any pair closer (centre-to-centre) than this can violate the gap.
    half_diags = [float(np.linalg.norm(hi - lo)) / 2.0 for lo, hi in boxes]
    radius = 2.0 * max(half_diags) + min_gap_mm
    tree = cKDTree(centroids)
    candidates = sorted(tree.query_pairs(r=radius))
    if not candidates:  # pragma: no cover - defensive
        candidates = list(combinations(range(len(tagged)), 2))

    findings = []
    for i, j in candidates:
        gap = aabb_gap(boxes[i], boxes[j])
        if gap < min_gap_mm:
            a, b = tagged[i].tag, tagged[j].tag
            verb = "overlaps" if gap <= 0 else f"is only {gap:.1f} mm from"
            findings.append(
                Finding(
                    severity="warning",
                    code="clearance",
                    message=f"component {a!r} {verb} {b!r} (min gap {min_gap_mm} mm)",
                    refs=(a, b),
                )
            )
    return findings


ALL_RULES = (
    duplicate_tags,
    unknown_part,
    unconnected_pins,
    empty_net,
    overcurrent,
    rotation_valid,
    clearance_violations,
)


def validate(project: Project) -> list[Finding]:
    """Run every rule; errors first, then warnings, each stably ordered."""
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(project))
    order = {"error": 0, "warning": 1}
    return sorted(findings, key=lambda f: (order.get(f.severity, 2), f.code, f.refs))
