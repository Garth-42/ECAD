"""JSON persistence: save/load the project model.

The library is never serialized — only ``part_number`` references are stored,
and a ``PartLibrary`` is injected on load. Output is human-readable and stable
(sorted keys, 2-space indent) so it diffs cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..library.parts import PartLibrary
from ..model.component import Component
from ..model.connectivity import Net, Wire
from ..model.geometry import Placement
from ..model.layout import Duct, MountingSurface
from ..model.project import Project

FORMAT_VERSION = 1


def _project_to_dict(project: Project) -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "components": {
            tag: {
                "part_number": c.part_number,
                "placement": {
                    "position": list(c.placement.position),
                    "rotation_deg": c.placement.rotation_deg,
                },
                "surface_id": c.surface_id,
            }
            for tag, c in sorted(project.components.items())
        },
        "nets": {
            net_id: {
                "name": n.name,
                "pins": sorted([tag, pin] for tag, pin in n.pins),
                "properties": n.properties,
            }
            for net_id, n in sorted(project.nets.items())
        },
        "wires": {
            wire_id: {
                "net_id": w.net_id,
                "source": list(w.source),
                "target": list(w.target),
                "number": w.number,
                "gauge": w.gauge,
                "color": w.color,
                "length_mm": w.length_mm,
                "path": [list(p) for p in w.path] if w.path is not None else None,
            }
            for wire_id, w in sorted(project.wires.items())
        },
        "surfaces": {
            sid: {"origin": list(s.origin), "size": list(s.size)}
            for sid, s in sorted(project.surfaces.items())
        },
        "ducts": {
            did: {"centerline": [list(p) for p in d.centerline], "width_mm": d.width_mm}
            for did, d in sorted(project.ducts.items())
        },
    }


def save(project: Project, path: str | Path) -> None:
    """Write the project to ``path`` as stable, human-readable JSON."""
    Path(path).write_text(json.dumps(_project_to_dict(project), indent=2, sort_keys=True) + "\n")


def load(path: str | Path, library: PartLibrary) -> Project:
    """Read a project JSON file and inject ``library``.

    Raises a clear error when a referenced part number is not in the library.
    """
    data = json.loads(Path(path).read_text())
    project = Project(name=data["name"], library=library)

    for tag, c in data.get("components", {}).items():
        if c["part_number"] not in library:
            raise ValueError(
                f"project {path}: component {tag!r} references unknown part "
                f"{c['part_number']!r}"
            )
        project.add_component(
            Component(
                tag=tag,
                part_number=c["part_number"],
                placement=Placement(
                    position=tuple(c["placement"]["position"]),
                    rotation_deg=c["placement"]["rotation_deg"],
                ),
                surface_id=c.get("surface_id"),
            )
        )

    for net_id, n in data.get("nets", {}).items():
        project.add_net(
            Net(
                id=net_id,
                name=n["name"],
                pins={(tag, pin) for tag, pin in n["pins"]},
                properties=n.get("properties", {}),
            )
        )

    for wire_id, w in data.get("wires", {}).items():
        project.wires[wire_id] = Wire(
            id=wire_id,
            net_id=w["net_id"],
            source=tuple(w["source"]),
            target=tuple(w["target"]),
            number=w["number"],
            gauge=w["gauge"],
            color=w["color"],
            length_mm=w["length_mm"],
            path=[tuple(p) for p in w["path"]] if w.get("path") is not None else None,
        )

    for sid, s in data.get("surfaces", {}).items():
        project.add_surface(
            MountingSurface(id=sid, origin=tuple(s["origin"]), size=tuple(s["size"]))
        )

    for did, d in data.get("ducts", {}).items():
        project.add_duct(
            Duct(
                id=did,
                centerline=[tuple(p) for p in d["centerline"]],
                width_mm=d["width_mm"],
            )
        )

    return project
