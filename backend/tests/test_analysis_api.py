from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from shapely.geometry import box, mapping
from sqlalchemy import select

from app.models import (
    AnalysisBoundary,
    AnalysisSnapshot,
    ChargingStation,
    CollectionRun,
    PoiQuality,
)
from app.services.analysis.job import digest, station_fingerprint, station_rows


@pytest.fixture
def saved_snapshot(demo_session):
    run = CollectionRun(id="c" * 32, status="completed", manifest={})
    demo_session.add(run)
    demo_session.flush()
    geometry = mapping(box(111, 27, 112, 28))
    for code, level in (("430100", "city"), ("430102", "district")):
        demo_session.add(
            AnalysisBoundary(
                adcode=code,
                city_code="430100",
                name="测试边界",
                level=level,
                geometry=geometry,
                source_url="https://example.org/test-boundary",
                coordinate_system="GCJ-02",
                content_hash=code.ljust(64, "0"),
            )
        )
    demo_session.flush()
    boundary_hash = digest(
        [
            (b.adcode, b.content_hash, b.source_url, b.coordinate_system)
            for b in sorted(demo_session.query(AnalysisBoundary).all(), key=lambda b: b.adcode)
        ]
    )
    feature = {
        "type": "Feature",
        "properties": {"code": "430102", "cityCode": "430100", "hotspot": True},
        "geometry": geometry,
    }
    result = {
        "metadata": {"stationCount": 0, "sourceUpdatedAt": None, "boundaryHash": boundary_hash},
        "province": {"count": 0},
        "regions": [{"code": "430100", "level": "city"}, {"code": "430102", "level": "district"}],
        "layers": {
            key: {"type": "FeatureCollection", "features": [feature]}
            for key in ("coverage", "uncovered", "grid")
        },
    }
    snapshot = AnalysisSnapshot(
        id="d" * 32,
        status="completed",
        algorithm_version="test-only",
        run_id=run.id,
        input_hash="x" * 64,
        boundary_hash=boundary_hash,
        parameters={},
        result=result,
    )
    demo_session.add(snapshot)
    demo_session.flush()
    return snapshot


def test_no_snapshot_is_explicit_404(client):
    assert client.get("/api/v1/analysis/latest").status_code == 404


def test_review_clue_snapshot_does_not_fall_back_to_all_scope(client, saved_snapshot, demo_session):
    assert client.get("/api/v1/analysis/latest?needs_review=true").status_code == 404
    result = deepcopy(saved_snapshot.result)
    scoped = AnalysisSnapshot(
        id="2" * 32,
        status="completed",
        algorithm_version="test-only",
        run_id=saved_snapshot.run_id,
        input_hash="b" * 64,
        boundary_hash=saved_snapshot.boundary_hash,
        parameters={"filters": {"needsReview": True}},
        result=result,
        computed_at=saved_snapshot.computed_at + timedelta(seconds=1),
    )
    demo_session.add(scoped)
    demo_session.flush()
    assert (
        client.get("/api/v1/analysis/latest?needs_review=true").json()["data"]["snapshotId"]
        == scoped.id
    )
    assert client.get("/api/v1/analysis/latest").json()["data"]["snapshotId"] == saved_snapshot.id


def test_latest_filters_select_exact_snapshot_without_full_dataset_fallback(
    client, saved_snapshot, demo_session
):
    result = deepcopy(saved_snapshot.result)
    result["metadata"]["datasetQualityRunIds"] = [saved_snapshot.run_id]
    result["province"]["count"] = 20
    scoped = AnalysisSnapshot(
        id="1" * 32,
        status="completed",
        algorithm_version="test-only",
        run_id=saved_snapshot.run_id,
        input_hash="a" * 64,
        boundary_hash=saved_snapshot.boundary_hash,
        parameters={"filters": {"classification": "personal"}},
        result=result,
        computed_at=saved_snapshot.computed_at + timedelta(seconds=1),
    )
    demo_session.add(scoped)
    demo_session.flush()
    assert client.get("/api/v1/analysis/latest").json()["data"]["snapshotId"] == saved_snapshot.id
    response = client.get("/api/v1/analysis/latest?classification=personal")
    assert response.json()["data"]["snapshotId"] == scoped.id
    assert response.json()["data"]["province"]["count"] == 20
    assert client.get("/api/v1/analysis/latest?classification=dedicated").status_code == 404
    assert (
        client.get(
            "/api/v1/analysis/latest?classification=personal&review_status=confirmed"
        ).status_code
        == 404
    )
    response = client.get(
        f"/api/v1/analysis/latest?classification=personal&batch={saved_snapshot.run_id}"
    )
    assert response.json()["data"]["snapshotId"] == scoped.id
    assert (
        client.get("/api/v1/analysis/latest?classification=personal&batch=" + "f" * 32).status_code
        == 404
    )


@pytest.mark.parametrize(
    "query", ["classification=invented", "review_status=done", "batch=invalid"]
)
def test_snapshot_filter_parameter_validation(client, query):
    assert client.get("/api/v1/analysis/latest?" + query).status_code == 422


def test_latest_projects_metadata_not_heavy_layers(client, saved_snapshot):
    response = client.get("/api/v1/analysis/latest")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["snapshotId"] == saved_snapshot.id
    assert not data["stale"]
    assert len(data["cities"]) == len(data["districts"]) == 1
    assert "layers" not in data
    assert [row["key"] for row in data["indicatorDefinitions"]] == [
        "count",
        "density",
        "coveragePercent",
    ]


def test_layer_is_pinned_scoped_and_bbox_filtered(client, saved_snapshot):
    response = client.get(
        f"/api/v1/analysis/layers/coverage?snapshot_id={saved_snapshot.id}&city=430100"
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["features"]) == 1
    assert (
        client.get("/api/v1/analysis/layers/coverage?bbox=113,29,114,30").json()["data"]["features"]
        == []
    )
    assert client.get("/api/v1/analysis/layers/coverage?bbox=114,30,113,29").status_code == 422
    assert client.get("/api/v1/analysis/layers/coverage?snapshot_id=" + "f" * 32).status_code == 404
    assert client.get("/api/v1/analysis/layers/imaginary").status_code == 422


def test_unknown_boundary_returns_404(client):
    assert client.get("/api/v1/analysis/boundaries?parent=439900").status_code == 404
    assert client.get("/api/v1/analysis/boundaries?parent=440000").status_code == 422


def test_layer_rejects_wrong_scope_and_keeps_snapshot_identity(client, saved_snapshot):
    assert client.get("/api/v1/analysis/layers/coverage?city=439900").status_code == 404
    assert client.get("/api/v1/analysis/layers/grid?city=430102").status_code == 422
    assert (
        client.get("/api/v1/analysis/layers/coverage?city=430100&adcode=430202").status_code == 422
    )
    result = client.get("/api/v1/analysis/layers/coverage?city=430100&adcode=430102").json()["data"]
    assert len(result["features"]) == 1 and result["snapshotId"] == saved_snapshot.id


def test_snapshot_detects_coordinate_and_quality_changes_without_count_change(
    client, saved_snapshot, demo_session
):
    station = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    station.source = "amap"
    quality = PoiQuality(
        station_id=station.id,
        classification="public_candidate",
        confidence="evidence_only",
        reasons=[],
        evidence={},
        needs_review=False,
        review_status="unreviewed",
        rules_version="test-v1",
        run_id=saved_snapshot.run_id,
    )
    demo_session.add(quality)
    demo_session.flush()
    result = deepcopy(saved_snapshot.result)
    result["metadata"].update(
        stationCount=1,
        sourceUpdatedAt=station.collected_at.isoformat() + "Z",
        stationHash=station_fingerprint(station_rows(demo_session)),
    )
    saved_snapshot.result = result
    demo_session.flush()
    assert not client.get("/api/v1/analysis/latest").json()["data"]["stale"]
    original = station.longitude
    station.longitude = original + Decimal("0.01")
    demo_session.flush()
    assert client.get("/api/v1/analysis/latest").json()["data"]["stale"]
    station.longitude = original
    quality.review_status = "confirmed"
    demo_session.flush()
    assert client.get("/api/v1/analysis/latest").json()["data"]["stale"]
