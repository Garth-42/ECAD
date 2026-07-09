"""Persistence backends: JSON (default) and SQLite (stretch goal).

``load_project``/``save_project`` dispatch on the file extension:
``.db`` / ``.sqlite`` / ``.sqlite3`` use the SQLite backend, everything else
uses JSON.
"""

from __future__ import annotations

from pathlib import Path

from ..library.parts import PartLibrary
from ..model.project import Project
from . import json_store, sqlite_store
from .json_store import load, save

SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _backend(path: str | Path):
    return sqlite_store if Path(path).suffix.lower() in SQLITE_SUFFIXES else json_store


def load_project(path: str | Path, library: PartLibrary) -> Project:
    return _backend(path).load(path, library)


def save_project(project: Project, path: str | Path) -> None:
    _backend(path).save(project, path)


__all__ = ["load", "load_project", "save", "save_project"]
