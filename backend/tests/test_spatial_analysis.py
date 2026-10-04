import math

import pytest
from shapely.geometry import Point, Polygon, box, mapping

from app.services.analysis.geometry import (
    assignment_check,
    coverage_union,
    grid_analysis,
    prepare_boundary,
    region_metrics,
    sample_buffer,
    sample_coverage_union,
    to_display,
    to_metric,
)


def test_duplicate_station_buffers_are_not_double_counted():
    point = Point(0, 0)
    union = coverage_union([point, point], radius_m=1000, quad_segs=24)
    single = coverage_union([point], radius_m=1000, quad_segs=24)
    assert union.area == pytest.approx(single.area)
    assert union.area == pytest.approx(math.pi * 1000**2, rel=0.001)


def test_coverage_is_clipped_and_uncovered_is_complement():
    boundary = box(0, 0, 2000, 2000)
    metrics, covered, uncovered = region_metrics(boundary, coverage_union([Point(0, 0)]), 2, 10)
    assert metrics["areaKm2"] == 4
    assert metrics["density"] == 0.5
    assert metrics["sharePercent"] == 20
    assert metrics["coveragePercent"] == pytest.approx(math.pi / 16 * 100, rel=0.001)
    assert covered.area + uncovered.area == pytest.approx(boundary.area)
    assert covered.intersection(uncovered).area == 0


def test_empty_samples_are_zero_coverage_without_fake_station():
    metrics, _, uncovered = region_metrics(box(0, 0, 1000, 1000), coverage_union([]), 0, 0)
    assert metrics["coveragePercent"] == 0
    assert metrics["sharePercent"] == 0
    assert uncovered.area == 1000000


def test_grid_uses_clipped_area_and_conserves_inside_samples():
    cells, metadata = grid_analysis(
        box(0, 0, 1500, 1000), [Point(100, 100), Point(1100, 100), Point(2000, 2000)], 1000
    )
    assert metadata["assignedCount"] == 2
    assert metadata["outsideBoundaryCount"] == 1
    assert sum(properties["count"] for _, properties in cells) == 2
    assert sum(properties["areaKm2"] for _, properties in cells) == pytest.approx(1.5)
    assert max(properties["density"] for _, properties in cells) == 2
    assert sum(properties["hotspot"] for _, properties in cells) == 1


def test_invalid_boundary_is_repaired_with_audit():
    bowtie = Polygon([(111, 27), (111.02, 27.02), (111.02, 27), (111, 27.02)])
    geometry, audit = prepare_boundary(mapping(bowtie))
    assert geometry.is_valid and geometry.area > 0
    assert audit["repaired"] and audit["method"]


def test_metric_chart_round_trip_does_not_claim_datum_conversion():
    point = Point(112.3, 28.1)
    result = to_display(to_metric(point))
    assert result.x == pytest.approx(point.x, abs=1e-8)
    assert result.y == pytest.approx(point.y, abs=1e-8)


def test_assignment_flags_mismatch_and_overlap_without_reassigning():
    result = assignment_check(
        {"a": box(0, 0, 2, 2), "b": box(1, 1, 3, 3)},
        [Point(1.5, 1.5), Point(0.5, 0.5), Point(8, 8)],
        ["a", "b", "a"],
    )
    assert result["multipleDistrictHitCount"] == 1
    assert result["outsideDistrictBoundaryCount"] == 1
    assert result["adcodeGeometryMismatchCount"] == 2


def test_invalid_parameters_fail():
    with pytest.raises(ValueError):
        coverage_union([Point(0, 0)], radius_m=0)
    with pytest.raises(ValueError):
        grid_analysis(box(0, 0, 10, 10), [], step_m=0)


@pytest.mark.parametrize("longitude,latitude", [(108.5, 25), (114, 30), (111.5, 27.5)])
def test_sample_ring_radius_uses_ellipsoid_scale_across_province(longitude, latitude):
    from pyproj import Geod

    ring = sample_buffer(Point(longitude, latitude))
    vertices = list(to_display(ring).exterior.coords)
    geod = Geod(ellps="WGS84")
    distances = [geod.inv(longitude, latitude, x, y)[2] for x, y in vertices]
    assert max(abs(distance - 1000) for distance in distances) < 0.0001
    # Independent area sanity check; finite polygon discretization is below 0.02%.
    assert ring.area == pytest.approx(math.pi * 1000**2, rel=0.0002)
    assert ring.is_valid


def test_sample_coverage_deduplicates_and_preserves_holes_and_complement():
    point = Point(112, 28)
    ring = sample_buffer(point)
    merged = sample_coverage_union([point, point])
    assert merged.area == pytest.approx(ring.area)
    center = to_metric(point)
    boundary = box(center.x - 1500, center.y - 1500, center.x + 1500, center.y + 1500)
    hole = box(center.x - 100, center.y - 100, center.x + 100, center.y + 100)
    boundary = boundary.difference(hole)
    metrics, covered, uncovered = region_metrics(boundary, merged, 1, 1)
    assert covered.intersection(hole).area == 0
    assert covered.area + uncovered.area == pytest.approx(boundary.area)
    assert metrics["coveredAreaKm2"] == pytest.approx((ring.area - hole.area) / 1e6)
    assert sample_coverage_union([]).is_empty


@pytest.mark.parametrize(
    "point,radius,segments",
    [(Point(112, 28), 0, 256), (Point(112, 90), 1000, 256), (Point(112, 28), 1000, 20)],
)
def test_sample_buffer_rejects_invalid_parameters(point, radius, segments):
    with pytest.raises(ValueError):
        sample_buffer(point, radius, segments)
