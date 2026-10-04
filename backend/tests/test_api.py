import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from app.db.seed import seed_demo
from app.db.session import get_session
from app.models import ChargingStation, StatisticSnapshot


def payload(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200 and body["message"] == "success"
    assert response.headers["X-Request-ID"]
    return body["data"]


def test_health(client):
    assert payload(client, "/api/health") == {"status": "ok", "database": "connected"}


def test_overview(client):
    data = payload(client, "/api/v1/overview")
    metrics = {metric["key"]: metric for metric in data["metrics"]}
    assert metrics["stations"]["value"] == 12000
    assert metrics["piles"]["value"] == 82300
    assert metrics["cities"]["value"] == 14
    assert metrics["stations"]["yoy"] == 23.3
    assert len(metrics["stations"]["sparkline"]) == 8
    assert data["sourceInfo"]["simulated"]
    assert data["statisticDate"] == "2026-09-30"


def test_database_session(demo_session):
    assert demo_session.execute(text("SELECT 1")).scalar_one() == 1
    assert demo_session.bind.dialect.name == "mysql"
    assert demo_session.scalar(select(func.count()).select_from(ChargingStation)) == 42


def test_regions(client):
    cities = payload(client, "/api/v1/regions")["items"]
    assert len(cities) == 14
    city = payload(client, "/api/v1/regions/430100")
    assert city["name"] == "长沙市" and city["stations"] == 2850
    assert city["density"] == 24.15
    assert all(city["simulated"] for city in cities)
    assert client.get("/api/v1/regions/999999").status_code == 404


@pytest.mark.parametrize(
    ("metric", "attribute"),
    [("station_count", "stations"), ("public_charger_count", "piles"), ("density", "density")],
)
def test_rankings(client, metric, attribute):
    rows = payload(client, f"/api/v1/rankings?metric={metric}")["items"]
    assert len(rows) == 14
    assert [row[attribute] for row in rows] == sorted(
        [row[attribute] for row in rows], reverse=True
    )


def test_trends(client):
    data = payload(client, "/api/v1/trends?adcode=430100")
    assert len(data["items"]) == 11
    assert data["items"][-1]["stations"] == 2850
    assert data["items"][-1]["statisticDate"] == "2026-09-30"


def test_stations_filters_and_pagination(client):
    first = payload(client, "/api/v1/stations?real_only=false&city=长沙&page_size=2")
    assert first["total"] == 3 and len(first["items"]) == 2
    second = payload(client, "/api/v1/stations?real_only=false&adcode=430100&page_size=2&page=2")
    assert len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["items"][0]["simulated"]
    assert payload(client, "/api/v1/stations?real_only=false&keyword=长沙")["total"] == 3
    assert (
        payload(client, "/api/v1/stations?real_only=false&keyword=%25")["total"] == 0
    )  # escaped SQL wildcard
    assert (
        payload(client, "/api/v1/stations?real_only=false&bbox=112.93,28.22,112.95,28.24")["total"]
        == 1
    )
    assert payload(client, "/api/v1/stations?real_only=false&page=999")["items"] == []


@pytest.mark.parametrize(
    "query",
    [
        "bbox=nan,1,2,3",
        "bbox=1,2,3",
        "bbox=181,0,182,1",
        "bbox=2,3,1,4",
        "page=0",
        "page_size=201",
        "city=长沙&adcode=430200",
        "adcode=123",
        "keyword=",
    ],
)
def test_invalid_station_query(client, query):
    response = client.get("/api/v1/stations?" + query)
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert "message" in response.json()


def test_sources_and_dashboard_contract(client):
    assert payload(client, "/api/v1/data-sources")["items"][0]["sourceType"] == "demo"
    data = payload(client, "/api/v1/dashboard")
    assert len(data["cities"]) == 14 and data["stations"] == []
    assert set(data["analysisGroups"]) == {"region", "scale"}
    for groups in data["analysisGroups"].values():
        assert sum(group["stations"] for group in groups) == 12000
    assert data["stationPage"]["total"] == 0
    assert payload(client, "/api/v1/cities/430100/districts")["status"] == "pending"


def test_snapshot_totals_and_seed_idempotence(demo_session):
    seed_demo(demo_session)
    assert demo_session.scalar(select(func.count()).select_from(ChargingStation)) == 42
    assert demo_session.scalar(select(func.count()).select_from(StatisticSnapshot)) == 165
    rows = list(demo_session.scalars(select(StatisticSnapshot)))
    for province in (row for row in rows if row.region_adcode == "430000"):
        children = [
            row
            for row in rows
            if row.region_adcode != "430000" and row.statistic_date == province.statistic_date
        ]
        for field in [
            "station_count",
            "public_charger_count",
            "dc_charger_count",
            "ac_charger_count",
        ]:
            assert sum(getattr(row, field) for row in children) == getattr(province, field)


def test_openapi_and_unregistered_analysis(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/overview" in spec["paths"]
    assert "data" in spec["components"]["schemas"]["APIResponse_Overview_"]["properties"]
    assert client.get("/docs").status_code == 200
    response = client.get("/api/v1/analysis/spatial")
    assert response.status_code == 404 and response.json()["code"] == 404


def test_cors(client):
    response = client.options(
        "/api/v1/overview",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options(
        "/api/v1/overview",
        headers={"Origin": "https://other.example", "Access-Control-Request-Method": "GET"},
    )
    assert denied.status_code == 400


@pytest.mark.parametrize(
    ("exception", "status"),
    [
        (OperationalError("private SQL", {}, Exception("private password")), 503),
        (RuntimeError("private password"), 500),
    ],
)
def test_error_envelopes_no_secrets(client, exception, status):
    def failing_session():
        raise exception

    client.app.dependency_overrides[get_session] = failing_session
    response = client.get("/api/v1/overview", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == status
    assert response.json()["code"] == status
    assert "private" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
