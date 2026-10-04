from datetime import timedelta

from shapely.geometry import box, mapping
from sqlalchemy import select

from app.models import (
    AnalysisBoundary,
    ChargingStation,
    CollectionRun,
    PlanningDataset,
    PlanningRun,
    PoiQuality,
    RoadODCache,
)
from app.models.entities import utc_now
from app.services.analysis.od_matrix import cache_key, cached_matrix, plan
from app.services.analysis.planning_replay import replay
from app.services.analysis.road import frozen_digest


def point(identity, position, population=None, candidate=False):
    row = {
        "id": identity,
        "name": "TEST ONLY " + identity,
        "position": position,
        "adcode": "430102",
        "source": "unit-test-only",
        "sourceUrl": "https://example.org/test-only",
        "year": 2026,
        "unit": "people",
        "variables": {} if population is None else {"population": population},
    }
    if candidate:
        row.update(poiId=identity, category="parking")
    return row


def install_inputs(client, session):
    boundary = session.get(AnalysisBoundary, "430102")
    if boundary is None:
        boundary = AnalysisBoundary(
            adcode="430102",
            city_code="430100",
            name="TEST ONLY",
            level="district",
            geometry=mapping(box(112.9, 28, 113.1, 28.2)),
            source_url="https://example.org/test-only",
            coordinate_system="GCJ-02",
            content_hash="c" * 64,
        )
        session.add(boundary)
        session.flush()
    demand = {
        "kind": "demand",
        "name": "TEST ONLY DEMAND",
        "batch": "test-demand-v1",
        "coordinateSystem": "GCJ-02",
        "records": [
            point("o1", [113, 28.1], 0),
            point("o2", [113.01, 28.1], 10),
            point("o3", [113.02, 28.1], 20),
        ],
    }
    candidates = {
        "kind": "candidates",
        "name": "TEST ONLY SITES",
        "batch": "test-sites-v1",
        "coordinateSystem": "GCJ-02",
        "records": [
            point("c1", [113.01, 28.1], candidate=True),
            point("c2", [113.02, 28.1], candidate=True),
        ],
    }
    response = client.post("/api/v1/analysis/planning/datasets", json=demand)
    assert response.status_code == 200
    did = response.json()["data"]["id"]
    assert client.post("/api/v1/analysis/planning/datasets", json=demand).json()["data"] == {
        "id": did,
        "reused": True,
    }
    cid = client.post("/api/v1/analysis/planning/datasets", json=candidates).json()["data"]["id"]
    return {
        "demandDatasetId": did,
        "candidateDatasetId": cid,
        "scopeCode": "430102",
        "weights": {"population": 1},
        "n": 1,
        "algorithm": "mclp",
        "metric": "straightDistanceM",
        "threshold": 500,
        "minExistingDistanceM": 0,
    }


def test_import_contract_traceable_real_input_run_and_missing_road_guard(client, demo_session):
    payload = install_inputs(client, demo_session)
    response = client.post("/api/v1/analysis/planning/optimization", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    persisted = demo_session.get(PlanningRun, data["id"])
    assert persisted.input_hash == frozen_digest(persisted.inputs)
    assert persisted.result["selectedIds"] == ["c2"]
    assert persisted.result["averageRoadTimeAfter"] is None
    assert persisted.result["dataBatches"] == ["test-demand-v1", "test-sites-v1"]
    assert persisted.inputs["problem"]["origins"][1]["weight"] == 0.5
    assert replay(demo_session, data["id"])["equal"]
    assert client.get("/api/v1/analysis/planning/runs/" + data["id"]).status_code == 200
    payload["metric"] = "durationSeconds"
    missing = client.post("/api/v1/analysis/planning/optimization", json=payload)
    assert missing.status_code == 409
    assert len(list(demo_session.scalars(select(PlanningRun)))) == 1
    estimate = client.post("/api/v1/analysis/planning/od-estimate", json=payload).json()["data"]
    assert estimate["apiCalls"] == 0 and estimate["estimatedCalls"] == 6
    records = demo_session.get(PlanningDataset, payload["candidateDatasetId"]).records
    assert records[0]["charger_count"] is None and records[0]["waiting_time"] is None


def test_import_rejects_missing_provenance_and_invalid_coordinates(client):
    bad = {
        "kind": "candidates",
        "name": "TEST ONLY",
        "batch": "test",
        "coordinateSystem": "GCJ-02",
        "records": [point("invalid", [0, 0], candidate=True)],
    }
    assert client.post("/api/v1/analysis/planning/datasets", json=bad).status_code == 422
    bad["records"][0]["position"] = [113, 28]
    del bad["records"][0]["sourceUrl"]
    assert client.post("/api/v1/analysis/planning/datasets", json=bad).status_code == 422


def test_od_cache_direction_expiry_dedup_and_no_network(session):
    origin = {"id": "o", "position": [113, 28]}
    destinations = [{"id": "a", "position": [113.01, 28]}, {"id": "b", "position": [113.01, 28]}]
    key = cache_key(origin["position"], destinations[0]["position"])
    assert key != cache_key(destinations[0]["position"], origin["position"])
    cached = RoadODCache(
        key=key,
        request={},
        response={"status": "ok", "durationSeconds": 120, "distanceM": 1300},
        fetched_at=utc_now(),
    )
    session.add(cached)
    session.flush()
    result = plan(session, [origin], destinations)
    assert (
        result["uniqueOD"] == 1 and result["validCacheHits"] == 1 and result["estimatedCalls"] == 0
    )
    assert len(cached_matrix(session, [origin], destinations)) == 2
    cached.fetched_at = utc_now() - timedelta(days=8)
    session.flush()
    assert plan(session, [origin], destinations)["estimatedCalls"] == 1
    assert cached_matrix(session, [origin], destinations)[0]["status"] == "missing"


def test_road_optimization_reads_complete_cached_od_and_computes_actual_route_means(
    client, demo_session
):
    payload = install_inputs(client, demo_session)
    station = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    station.source, station.longitude, station.latitude = "amap", 113.05, 28.1
    station.poi_id = "TEST-BASELINE"
    batch = CollectionRun(id="a" * 32, status="completed", manifest={"testOnly": True})
    demo_session.add(batch)
    demo_session.flush()
    demo_session.add(
        PoiQuality(
            station_id=station.id,
            classification="public_candidate",
            confidence="test-only",
            reasons=[],
            evidence={"testOnly": True},
            needs_review=False,
            review_status="unreviewed",
            rules_version="test-only",
            run_id=batch.id,
        )
    )
    demo_session.flush()
    demand = demo_session.get(PlanningDataset, payload["demandDatasetId"]).records
    sites = demo_session.get(PlanningDataset, payload["candidateDatasetId"]).records
    for origin in demand:
        for destination, seconds in [(s, 120 if s["id"] == "c2" else 600) for s in sites] + [
            ({"position": [113.05, 28.1]}, 900)
        ]:
            key = cache_key(origin["position"], destination["position"])
            demo_session.add(
                RoadODCache(
                    key=key,
                    request={},
                    response={"status": "ok", "durationSeconds": seconds, "distanceM": 1000},
                    fetched_at=utc_now(),
                )
            )
    demo_session.flush()
    payload.update(metric="durationSeconds", threshold=300)
    response = client.post("/api/v1/analysis/planning/optimization", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    result = data["result"]
    assert result["selectedIds"] == ["c2"]
    assert result["averageRoadTimeBefore"] == {"seconds": 900, "validOriginCount": 3}
    assert result["averageRoadTimeAfter"] == {"seconds": 120, "validOriginCount": 3}
    assert result["before"]["coveredWeight"] == 0
    assert result["after"]["coveredWeight"] == 1.5
    assert replay(demo_session, data["id"])["equal"]


def test_estimate_uses_scope_constraints_and_includes_baseline(client, demo_session):
    payload = install_inputs(client, demo_session)
    # Outside the administrative polygon but within the import coordinate envelope.
    dataset = demo_session.get(PlanningDataset, payload["candidateDatasetId"])
    dataset.records = dataset.records + [point("outside", [114, 29], candidate=True)]
    demo_session.flush()
    response = client.post("/api/v1/analysis/planning/od-estimate", json=payload)
    data = response.json()["data"]
    assert data["candidateCount"] == 2 and data["originCount"] == 3
    assert data["candidateUniqueOD"] == 6 and data["baselineUniqueOD"] == 0
    assert data["originsWithoutExistingCandidates"] == ["o1", "o2", "o3"]
    preview = client.post(
        "/api/v1/analysis/planning/demand-preview",
        json={"datasetId": payload["demandDatasetId"], "weights": {"population": 1}},
    )
    assert preview.status_code == 200 and preview.json()["data"]["completeCount"] == 3
