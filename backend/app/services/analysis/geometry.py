"""Deterministic sample geometry; GCJ-02 chart metrics are explicitly approximate."""

import math
from collections import Counter

from pyproj import Geod, Transformer
from shapely import STRtree, make_valid, union_all
from shapely.geometry import GeometryCollection, Polygon, box, mapping, shape
from shapely.ops import transform

METRIC_PIPELINE = (
    "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
    "+step +proj=laea +lat_0=27.5 +lon_0=111.5 +ellps=WGS84"
)
PROJECT = Transformer.from_pipeline(METRIC_PIPELINE)
SCALE_GEOD = Geod(ellps="WGS84")
COORDINATE_NOTICE = (
    "GCJ-02坐标图上的局部LAEA米制近似，椭球参数仅用于尺度模型，"
    "未将GCJ-02宣称为WGS84、未做官方基准转换或实地校准。"
    "1km为模型直线样本缓冲范围，不代表道路可达、真实营业或人口覆盖。"
)


def to_metric(geometry):
    return transform(PROJECT.transform, geometry)


def to_display(geometry):
    return transform(lambda x, y, z=None: PROJECT.transform(x, y, direction="INVERSE"), geometry)


def polygons_only(geometry):
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    polygons = []
    if hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            candidate = polygons_only(part)
            if not candidate.is_empty:
                polygons.extend(
                    candidate.geoms if candidate.geom_type == "MultiPolygon" else [candidate]
                )
    return union_all(polygons) if polygons else GeometryCollection()


def prepare_boundary(raw_geometry):
    original = to_metric(shape(raw_geometry))
    repaired = not original.is_valid
    geometry = polygons_only(make_valid(original)) if repaired else original
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError("边界无法形成有效面，停止分析")
    return geometry, {
        "repaired": repaired,
        "method": "GEOS make_valid + polygons_only" if repaired else None,
        "originalAreaKm2": original.area / 1e6,
        "repairedAreaKm2": geometry.area / 1e6,
        "areaChangeKm2": (geometry.area - original.area) / 1e6,
    }


def coverage_union(points, radius_m=1000, quad_segs=24):
    if radius_m <= 0 or not math.isfinite(radius_m) or quad_segs < 8:
        raise ValueError("无效的缓冲参数")
    return union_all([point.buffer(radius_m, quad_segs=quad_segs) for point in points])


def sample_buffer(point, radius_m=1000, segments=256):
    """Ellipsoid-scale ring on GCJ coordinates, then equal-area projection.

    This controls radial projection distortion; it is not a datum conversion.
    GEOS union/clip and area still operate in the shared LAEA metric plane.
    """
    if (
        not math.isfinite(radius_m)
        or radius_m <= 0
        or not isinstance(segments, int)
        or segments < 96
        or point.is_empty
        or not math.isfinite(point.x)
        or not math.isfinite(point.y)
        or not -180 <= point.x <= 180
        or not -90 < point.y < 90
    ):
        raise ValueError("无效的样本坐标或缓冲参数")
    azimuths = [360 * index / segments for index in range(segments)]
    longitude, latitude, _ = SCALE_GEOD.fwd(
        [point.x] * segments, [point.y] * segments, azimuths, [radius_m] * segments
    )
    return to_metric(Polygon(zip(longitude, latitude, strict=True)))


def sample_coverage_union(points, radius_m=1000, segments=256):
    return union_all([sample_buffer(point, radius_m, segments) for point in points])


def region_metrics(boundary, coverage, count, total):
    covered = boundary.intersection(coverage)
    uncovered = boundary.difference(coverage)
    area = boundary.area / 1e6
    return (
        {
            "count": count,
            "sharePercent": count / total * 100 if total else 0,
            "areaKm2": area,
            "density": count / area,
            "coveredAreaKm2": covered.area / 1e6,
            "coveragePercent": min(100.0, max(0.0, covered.area / boundary.area * 100)),
            "uncoveredAreaKm2": uncovered.area / 1e6,
        },
        covered,
        uncovered,
    )


def display_feature(geometry, properties, tolerance_m=25):
    # Simplification is for transport only. Indicators use the exact computed geometry.
    simplified = geometry.simplify(tolerance_m, preserve_topology=True)
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": mapping(to_display(simplified)),
    }


def grid_analysis(boundary, points, step_m=5000):
    if not math.isfinite(step_m) or step_m < 1000 or step_m > 20000:
        raise ValueError("网格边长必须在1–20km之间")
    counts = Counter()
    outside = 0
    for point in points:
        if not boundary.covers(point):
            outside += 1
            continue
        counts[(math.floor(point.x / step_m), math.floor(point.y / step_m))] += 1
    west, south, east, north = boundary.bounds
    cells = []
    for x in range(math.floor(west / step_m), math.floor(east / step_m) + 1):
        for y in range(math.floor(south / step_m), math.floor(north / step_m) + 1):
            cell = box(x * step_m, y * step_m, (x + 1) * step_m, (y + 1) * step_m).intersection(
                boundary
            )
            if cell.is_empty or cell.area < 1:
                continue
            count = counts[(x, y)]
            cells.append(
                (
                    cell,
                    {
                        "id": f"{x}:{y}",
                        "count": count,
                        "areaKm2": cell.area / 1e6,
                        "density": count / (cell.area / 1e6),
                    },
                )
            )
    positive = sorted(properties["density"] for _, properties in cells if properties["count"] > 0)
    if sum(properties["count"] for _, properties in cells) != sum(counts.values()):
        raise ValueError("网格裁切后样本计数不守恒，请核验网格边缘点；不保存不完整结果")
    # Descriptive upper quantile, not Gi*, DBSCAN or a significance test.
    threshold = positive[math.ceil(len(positive) * 0.95) - 1] if positive else None
    for _, properties in cells:
        properties["hotspot"] = bool(
            threshold is not None and properties["count"] > 0 and properties["density"] >= threshold
        )
    return cells, {
        "stepM": step_m,
        "cellCount": len(cells),
        "assignedCount": sum(counts.values()),
        "outsideBoundaryCount": outside,
        "hotspotThreshold": threshold,
        "hotspotMethod": "有样本网格密度P95描述性阈值，非统计显著热点",
    }


def assignment_check(boundaries, points, adcodes):
    tree = STRtree(list(boundaries.values()))
    keys = list(boundaries)
    mismatch = outside = ambiguous = 0
    evidence = []
    for index, (point, adcode) in enumerate(zip(points, adcodes, strict=True)):
        hits = [keys[int(index)] for index in tree.query(point, predicate="intersects")]
        outside += int(not hits)
        ambiguous += int(len(hits) > 1)
        mismatch += int(adcode not in hits)
        if adcode not in hits or len(hits) != 1:
            evidence.append({"sampleIndex": index, "sourceAdcode": adcode, "geometryAdcodes": hits})
    return {
        "adcodeGeometryMismatchCount": mismatch,
        "outsideDistrictBoundaryCount": outside,
        "multipleDistrictHitCount": ambiguous,
        "evidence": evidence,
        "notice": "行政区数量按原始adcode；空间网格按几何归属。错配保留原记录，不自动改址。",
    }
