"""Bill of materials view: components grouped by part number."""

from __future__ import annotations

from dataclasses import dataclass

from ..model.project import Project


@dataclass(frozen=True)
class BomRow:
    part_number: str
    manufacturer: str
    description: str
    quantity: int
    tags: tuple[str, ...]


def bom(project: Project) -> list[BomRow]:
    by_part: dict[str, list[str]] = {}
    for c in project.iter_components():
        by_part.setdefault(c.part_number, []).append(c.tag)
    rows = []
    for part_number in sorted(by_part):
        part = project.library.get(part_number)
        tags = tuple(sorted(by_part[part_number]))
        rows.append(
            BomRow(
                part_number=part_number,
                manufacturer=part.manufacturer,
                description=part.description,
                quantity=len(tags),
                tags=tags,
            )
        )
    return rows


def render_bom(project: Project) -> str:
    lines = [
        f"BILL OF MATERIALS — {project.name}",
        "",
        f"{'QTY':<4} {'PART NUMBER':<16} {'MANUFACTURER':<20} {'TAGS':<12} DESCRIPTION",
    ]
    for r in bom(project):
        tags = ",".join(r.tags)
        lines.append(
            f"{r.quantity:<4} {r.part_number:<16} {r.manufacturer:<20} {tags:<12} {r.description}"
        )
    return "\n".join(lines) + "\n"
