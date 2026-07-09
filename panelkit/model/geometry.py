"""Geometry primitives: placements, bounding boxes, transforms.

All units are millimetres; all angles degrees. Rotation is restricted to
{0, 90, 180, 270} about the Z axis (the backplate normal), which keeps every
world bounding box axis-aligned.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ALLOWED_ROTATIONS: frozenset[int] = frozenset({0, 90, 180, 270})

# Exact integer rotation matrices for the four allowed angles (row-major 2x2).
_ROT2D: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {
    0: ((1, 0), (0, 1)),
    90: ((0, -1), (1, 0)),
    180: ((-1, 0), (0, -1)),
    270: ((0, 1), (-1, 0)),
}


class InvalidRotationError(ValueError):
    """Raised when a placement rotation is not one of {0, 90, 180, 270}."""


def _check_rotation(rotation_deg: int) -> int:
    if rotation_deg not in ALLOWED_ROTATIONS:
        raise InvalidRotationError(
            f"rotation_deg must be one of {sorted(ALLOWED_ROTATIONS)}, got {rotation_deg!r}"
        )
    return rotation_deg


@dataclass(frozen=True)
class Placement:
    """World pose of a component: a translation plus a Z rotation."""

    position: tuple[float, float, float]
    rotation_deg: int = 0

    def __post_init__(self) -> None:
        _check_rotation(self.rotation_deg)

    def to_matrix(self) -> np.ndarray:
        """Return the 4x4 homogeneous transform (rotation about Z, then translate)."""
        r = _ROT2D[self.rotation_deg]
        m = np.eye(4)
        m[0, 0], m[0, 1] = r[0]
        m[1, 0], m[1, 1] = r[1]
        m[0, 3], m[1, 3], m[2, 3] = self.position
        return m


def transform_point(local_xyz: tuple[float, float, float], placement: Placement) -> np.ndarray:
    """Transform a local point into world space under the placement."""
    p = np.array([*local_xyz, 1.0])
    return (placement.to_matrix() @ p)[:3]


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in the part's local frame, anchored at the local origin."""

    size: tuple[float, float, float]

    def world_aabb(self, placement: Placement) -> tuple[np.ndarray, np.ndarray]:
        """Return (min_xyz, max_xyz) of the box in world space.

        The local box spans [0, w] x [0, h] x [0, d]. Under a 90/270 degree
        rotation the world footprint swaps width and height; the offsets from
        the placement origin follow the rotated corners.
        """
        w, h, d = self.size
        corners_local = np.array(
            [
                [0.0, 0.0, 0.0],
                [w, 0.0, 0.0],
                [0.0, h, 0.0],
                [w, h, 0.0],
                [0.0, 0.0, d],
                [w, h, d],
            ]
        )
        m = placement.to_matrix()
        pts = (m @ np.hstack([corners_local, np.ones((len(corners_local), 1))]).T).T[:, :3]
        return pts.min(axis=0), pts.max(axis=0)


def aabb_gap(
    a: tuple[np.ndarray, np.ndarray], b: tuple[np.ndarray, np.ndarray]
) -> float:
    """Axis-aligned gap between two AABBs.

    Positive: minimum separation distance. Zero or negative: the boxes touch
    or overlap (the magnitude is the smallest overlap depth).
    """
    a_min, a_max = a
    b_min, b_max = b
    # Per-axis signed separation: positive means a gap on that axis.
    sep = np.maximum(b_min - a_max, a_min - b_max)
    if np.any(sep > 0):
        pos = np.clip(sep, 0.0, None)
        return float(np.linalg.norm(pos))
    return float(sep.max())
