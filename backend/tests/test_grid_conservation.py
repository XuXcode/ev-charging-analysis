import pytest
from shapely.geometry import Point, box

from app.services.analysis.geometry import grid_analysis


def test_degenerate_boundary_grid_cannot_silently_drop_a_sample():
    with pytest.raises(ValueError, match="计数不守恒"):
        grid_analysis(box(0, 0, 5000, 5000), [Point(5000, 5000)])
