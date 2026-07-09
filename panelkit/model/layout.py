"""Mounting surfaces and wire ducts (routing geometry)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MountingSurface:
    id: str
    origin: tuple[float, float, float]
    size: tuple[float, float]


@dataclass
class Duct:
    id: str
    centerline: list[tuple[float, float, float]] = field(default_factory=list)
    width_mm: float = 40.0
