import pytest
from sqlalchemy import select

from app.models import AnalysisScopeQuality, ChargingStation, CollectionRun, DataSource, PoiQuality


@pytest.fixture
def governed_stations(demo_session):
    rows = list(demo_session.scalars(select(ChargingStation).order_by(ChargingStation.id).limit(3)))
    run = CollectionRun(id="d" * 32, status="completed", manifest={})
    demo_session.add(run)
    demo_session.flush()
    for row, kind, status in zip(
        rows,
        ["personal", "public_candidate", "unknown"],
        ["unreviewed", "confirmed", "needs_review"],
        strict=True,
    ):
        row.source = "amap"
        row.adcode = "430102"
        demo_session.get(DataSource, row.data_source_id).is_demo = False
        demo_session.add(
            PoiQuality(
                station_id=row.id,
                classification=kind,
                review_status=status,
                confidence="evidence_only",
                needs_review=kind != "public_candidate",
                reasons=[],
                evidence={},
                rules_version="test",
                run_id=run.id,
            )
        )
    demo_session.add(
        AnalysisScopeQuality(
            adcode="430102",
            city_code="430100",
            name="测试范围",
            completeness_warning=True,
            run_id=run.id,
        )
    )
    demo_session.flush()
    return rows, run.id


def test_station_quality_filters_are_intersections_with_trace(client, governed_stations):
    rows, batch = governed_stations
    params = {
        "city": "430100",
        "adcode": "430102",
        "classification": "personal",
        "review_status": "unreviewed",
        "batch": batch,
    }
    response = client.get("/api/v1/stations", params=params)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == str(rows[0].id)
    assert item["classification"] == "personal"
    assert item["reviewStatus"] == "unreviewed"
    assert item["batch"] == batch and item["completenessWarning"]
    assert "evidence" not in item
    params["review_status"] = "confirmed"
    assert client.get("/api/v1/stations", params=params).json()["data"]["total"] == 0


def test_quality_and_station_filters_agree(client, governed_stations):
    _, batch = governed_stations
    common = {
        "adcode": "430102",
        "classification": "unknown",
        "review_status": "needs_review",
        "batch": batch,
    }
    stations = client.get("/api/v1/stations", params=common).json()["data"]
    quality = client.get("/api/v1/quality/pois", params={**common, "all_records": True}).json()[
        "data"
    ]
    assert stations["total"] == quality["total"] == 1
    assert stations["items"][0]["poiId"] == quality["items"][0]["poiId"]
    assert (
        client.get("/api/v1/quality/pois", params={**common, "bbox": "0,0,1,1"}).json()["data"][
            "total"
        ]
        == 0
    )


def test_rule_review_clues_are_distinct_from_manual_state(client, governed_stations):
    response = client.get("/api/v1/stations", params={"city": "430100", "needs_review": True})
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 2
    assert (
        client.get(
            "/api/v1/stations",
            params={"city": "430100", "needs_review": True, "review_status": "unreviewed"},
        ).json()["data"]["total"]
        == 1
    )
    assert (
        client.get(
            "/api/v1/stations",
            params={"city": "430100", "needs_review": True, "classification": "public_candidate"},
        ).json()["data"]["total"]
        == 0
    )
    assert (
        client.get("/api/v1/stations", params={"city": "430100", "needs_review": False}).json()[
            "data"
        ]["total"]
        == 1
    )


def test_keyword_search_id_address_pagination_and_literal_wildcards(client, governed_stations):
    rows, batch = governed_stations
    for index, row in enumerate(rows):
        row.poi_id = f"SEARCH-ID-{index}"
        row.name = f"测试充电设施{index}"
        row.address = "共同地址_100%" if index == 0 else "共同地址"
    common = {"batch": batch, "city": "430100", "adcode": "430102"}
    by_id = client.get("/api/v1/stations", params={**common, "keyword": "SEARCH-ID-1"}).json()[
        "data"
    ]
    assert by_id["total"] == 1 and by_id["items"][0]["id"] == str(rows[1].id)
    first = client.get(
        "/api/v1/stations", params={**common, "keyword": "共同地址", "page_size": 1}
    ).json()["data"]
    second = client.get(
        "/api/v1/stations", params={**common, "keyword": "共同地址", "page_size": 1, "page": 2}
    ).json()["data"]
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]
    literal = client.get("/api/v1/stations", params={**common, "keyword": "_100%"}).json()["data"]
    assert literal["total"] == 1
    assert (
        client.get(
            "/api/v1/stations",
            params={**common, "keyword": "SEARCH-ID-1", "classification": "personal"},
        ).json()["data"]["total"]
        == 0
    )


@pytest.mark.parametrize("endpoint", ["/api/v1/stations", "/api/v1/quality/pois"])
@pytest.mark.parametrize(
    "params",
    [
        {"classification": "official"},
        {"review_status": "open"},
        {"batch": "secret"},
        {"bbox": "120,30,110,20"},
        {"page": 0},
        {"page_size": 1000},
    ],
)
def test_invalid_filters_rejected(client, endpoint, params):
    assert client.get(endpoint, params=params).status_code == 422


@pytest.mark.parametrize("endpoint", ["/api/v1/stations", "/api/v1/quality/pois"])
def test_missing_batch_is_not_silently_current_data(client, endpoint):
    assert client.get(endpoint, params={"batch": "f" * 32}).status_code == 404
