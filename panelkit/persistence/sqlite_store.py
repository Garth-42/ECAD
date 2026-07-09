"""SQLite persistence backend (spec section 11 stretch goal).

Same interface as ``json_store``: ``save(project, path)`` / ``load(path,
library)``. The schema is one table per model collection; nested point lists
(wire paths, duct centerlines) and free-form properties are stored as JSON
text columns. The library is never stored — only ``part_number`` references.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..library.parts import PartLibrary
from ..model.component import Component
from ..model.connectivity import Net, Wire
from ..model.geometry import Placement
from ..model.layout import Duct, MountingSurface
from ..model.project import Project

FORMAT_VERSION = 1

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE components (
    tag TEXT PRIMARY KEY,
    part_number TEXT NOT NULL,
    pos_x REAL NOT NULL, pos_y REAL NOT NULL, pos_z REAL NOT NULL,
    rotation_deg INTEGER NOT NULL,
    surface_id TEXT
);
CREATE TABLE nets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    properties TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE net_pins (
    net_id TEXT NOT NULL REFERENCES nets(id),
    tag TEXT NOT NULL,
    pin TEXT NOT NULL,
    PRIMARY KEY (net_id, tag, pin)
);
CREATE TABLE wires (
    id TEXT PRIMARY KEY,
    net_id TEXT NOT NULL,
    source_tag TEXT NOT NULL, source_pin TEXT NOT NULL,
    target_tag TEXT NOT NULL, target_pin TEXT NOT NULL,
    number TEXT NOT NULL,
    gauge TEXT NOT NULL,
    color TEXT NOT NULL,
    length_mm REAL,
    path TEXT
);
CREATE TABLE surfaces (
    id TEXT PRIMARY KEY,
    origin_x REAL NOT NULL, origin_y REAL NOT NULL, origin_z REAL NOT NULL,
    width REAL NOT NULL, height REAL NOT NULL
);
CREATE TABLE ducts (
    id TEXT PRIMARY KEY,
    width_mm REAL NOT NULL,
    centerline TEXT NOT NULL
);
"""


def save(project: Project, path: str | Path) -> None:
    """Write the project to an SQLite database, replacing any existing file."""
    db_path = Path(path)
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_SCHEMA)
        con.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("format_version", str(FORMAT_VERSION)), ("name", project.name)],
        )
        con.executemany(
            "INSERT INTO components VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c.tag,
                    c.part_number,
                    *c.placement.position,
                    c.placement.rotation_deg,
                    c.surface_id,
                )
                for c in project.iter_components()
            ],
        )
        con.executemany(
            "INSERT INTO nets VALUES (?, ?, ?)",
            [(n.id, n.name, json.dumps(n.properties, sort_keys=True)) for n in project.iter_nets()],
        )
        con.executemany(
            "INSERT INTO net_pins VALUES (?, ?, ?)",
            [(n.id, tag, pin) for n in project.iter_nets() for tag, pin in sorted(n.pins)],
        )
        con.executemany(
            "INSERT INTO wires VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    w.id,
                    w.net_id,
                    *w.source,
                    *w.target,
                    w.number,
                    w.gauge,
                    w.color,
                    w.length_mm,
                    json.dumps([list(p) for p in w.path]) if w.path is not None else None,
                )
                for w in project.iter_wires()
            ],
        )
        con.executemany(
            "INSERT INTO surfaces VALUES (?, ?, ?, ?, ?, ?)",
            [
                (s.id, *s.origin, *s.size)
                for s in (project.surfaces[k] for k in sorted(project.surfaces))
            ],
        )
        con.executemany(
            "INSERT INTO ducts VALUES (?, ?, ?)",
            [
                (d.id, d.width_mm, json.dumps([list(p) for p in d.centerline]))
                for d in (project.ducts[k] for k in sorted(project.ducts))
            ],
        )
        con.commit()
    finally:
        con.close()


def load(path: str | Path, library: PartLibrary) -> Project:
    """Read a project database and inject ``library``; fails loudly on bad refs."""
    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(f"no such project database: {db_path}")
    con = sqlite3.connect(db_path)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta"))
        project = Project(name=meta["name"], library=library)

        for tag, part_number, x, y, z, rot, surface_id in con.execute(
            "SELECT tag, part_number, pos_x, pos_y, pos_z, rotation_deg, surface_id"
            " FROM components ORDER BY tag"
        ):
            if part_number not in library:
                raise ValueError(
                    f"project {db_path}: component {tag!r} references unknown part "
                    f"{part_number!r}"
                )
            project.add_component(
                Component(
                    tag=tag,
                    part_number=part_number,
                    placement=Placement(position=(x, y, z), rotation_deg=rot),
                    surface_id=surface_id,
                )
            )

        pins_by_net: dict[str, set[tuple[str, str]]] = {}
        for net_id, tag, pin in con.execute("SELECT net_id, tag, pin FROM net_pins"):
            pins_by_net.setdefault(net_id, set()).add((tag, pin))
        for net_id, name, properties in con.execute(
            "SELECT id, name, properties FROM nets ORDER BY id"
        ):
            project.add_net(
                Net(
                    id=net_id,
                    name=name,
                    pins=pins_by_net.get(net_id, set()),
                    properties=json.loads(properties),
                )
            )

        for row in con.execute(
            "SELECT id, net_id, source_tag, source_pin, target_tag, target_pin,"
            " number, gauge, color, length_mm, path FROM wires ORDER BY id"
        ):
            wire_id, net_id, s_tag, s_pin, t_tag, t_pin, number, gauge, color, length, path = row
            project.wires[wire_id] = Wire(
                id=wire_id,
                net_id=net_id,
                source=(s_tag, s_pin),
                target=(t_tag, t_pin),
                number=number,
                gauge=gauge,
                color=color,
                length_mm=length,
                path=[tuple(p) for p in json.loads(path)] if path is not None else None,
            )

        for sid, ox, oy, oz, w, h in con.execute(
            "SELECT id, origin_x, origin_y, origin_z, width, height FROM surfaces ORDER BY id"
        ):
            project.add_surface(MountingSurface(id=sid, origin=(ox, oy, oz), size=(w, h)))

        for did, width_mm, centerline in con.execute(
            "SELECT id, width_mm, centerline FROM ducts ORDER BY id"
        ):
            project.add_duct(
                Duct(
                    id=did,
                    centerline=[tuple(p) for p in json.loads(centerline)],
                    width_mm=width_mm,
                )
            )

        return project
    finally:
        con.close()
