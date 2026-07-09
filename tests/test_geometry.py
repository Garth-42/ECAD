"""M1: transform math, placements, bounding boxes."""

import numpy as np
import pytest

from panelkit.model.geometry import (
    BoundingBox,
    InvalidRotationError,
    Placement,
    aabb_gap,
    transform_point,
)


class TestPlacement:
    def test_identity_matrix(self) -> None:
        m = Placement(position=(0, 0, 0), rotation_deg=0).to_matrix()
        assert np.allclose(m, np.eye(4))

    def test_translation(self) -> None:
        p = Placement(position=(10.0, 20.0, 5.0))
        assert np.allclose(transform_point((1.0, 2.0, 3.0), p), [11.0, 22.0, 8.0])

    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [
            (0, (1.0, 2.0, 3.0)),
            (90, (-2.0, 1.0, 3.0)),
            (180, (-1.0, -2.0, 3.0)),
            (270, (2.0, -1.0, 3.0)),
        ],
    )
    def test_rotation(self, rotation: int, expected: tuple[float, float, float]) -> None:
        p = Placement(position=(0, 0, 0), rotation_deg=rotation)
        assert np.allclose(transform_point((1.0, 2.0, 3.0), p), expected)

    def test_rotation_then_translation(self) -> None:
        p = Placement(position=(100.0, 50.0, 0.0), rotation_deg=90)
        # (10, 0, 0) rotates to (0, 10, 0), then translates.
        assert np.allclose(transform_point((10.0, 0.0, 0.0), p), [100.0, 60.0, 0.0])

    @pytest.mark.parametrize("bad", [45, -90, 360, 1])
    def test_invalid_rotation_rejected(self, bad: int) -> None:
        with pytest.raises(InvalidRotationError):
            Placement(position=(0, 0, 0), rotation_deg=bad)


class TestBoundingBox:
    def test_world_aabb_no_rotation(self) -> None:
        box = BoundingBox(size=(30.0, 20.0, 10.0))
        lo, hi = box.world_aabb(Placement(position=(100.0, 200.0, 0.0)))
        assert np.allclose(lo, [100.0, 200.0, 0.0])
        assert np.allclose(hi, [130.0, 220.0, 10.0])

    def test_world_aabb_90_swaps_footprint(self) -> None:
        box = BoundingBox(size=(30.0, 20.0, 10.0))
        lo, hi = box.world_aabb(Placement(position=(0.0, 0.0, 0.0), rotation_deg=90))
        # Width and height swap; box extends into -X after a +90 rotation.
        assert np.allclose(hi - lo, [20.0, 30.0, 10.0])
        assert np.allclose(lo, [-20.0, 0.0, 0.0])

    def test_world_aabb_180(self) -> None:
        box = BoundingBox(size=(30.0, 20.0, 10.0))
        lo, hi = box.world_aabb(Placement(position=(0.0, 0.0, 0.0), rotation_deg=180))
        assert np.allclose(hi - lo, [30.0, 20.0, 10.0])
        assert np.allclose(lo, [-30.0, -20.0, 0.0])


class TestAabbGap:
    def test_separated(self) -> None:
        a = (np.array([0.0, 0.0, 0.0]), np.array([10.0, 10.0, 10.0]))
        b = (np.array([15.0, 0.0, 0.0]), np.array([25.0, 10.0, 10.0]))
        assert aabb_gap(a, b) == pytest.approx(5.0)

    def test_overlapping(self) -> None:
        a = (np.array([0.0, 0.0, 0.0]), np.array([10.0, 10.0, 10.0]))
        b = (np.array([5.0, 0.0, 0.0]), np.array([15.0, 10.0, 10.0]))
        assert aabb_gap(a, b) <= 0.0

    def test_diagonal_gap_is_euclidean(self) -> None:
        a = (np.array([0.0, 0.0, 0.0]), np.array([10.0, 10.0, 10.0]))
        b = (np.array([13.0, 14.0, 0.0]), np.array([20.0, 20.0, 10.0]))
        assert aabb_gap(a, b) == pytest.approx(5.0)  # 3-4-5 triangle
