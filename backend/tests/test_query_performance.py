from sqlalchemy import event

from app.models import ChargingStation
from app.services.data import DataService


def test_station_page_serialization_has_no_per_row_source_or_deferred_queries(demo_session):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    demo_session.expire_all()
    connection = demo_session.connection()
    event.listen(connection, "before_cursor_execute", capture)
    try:
        service = DataService(demo_session)
        rows, total = service.stations.page(page=1, page_size=200, real_only=False)
        assert rows and total >= len(rows)
        data = [service.station_view(row) for row in rows]
        assert len(data) == len(rows)
        station_selects = [sql for sql in statements if "from charging_stations" in sql]
        source_selects = [sql for sql in statements if "from data_sources" in sql]
        assert len(station_selects) == 2  # count + projected page; no deferred-column fetches
        assert len(source_selects) <= len({row.data_source_id for row in rows})
        assert "identity_hash" not in station_selects[1]
    finally:
        event.remove(connection, "before_cursor_execute", capture)


def test_large_api_responses_are_compressed(client):
    response = client.get(
        "/api/v1/stations?real_only=false&page_size=200", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == "gzip"
    assert response.json()["data"]["items"]


def test_id_first_page_preserves_filtered_count_order_and_offsets(demo_session):
    service = DataService(demo_session)
    first = demo_session.scalar(service.stations.query(real_only=False).limit(1))
    assert first is not None
    cases = [
        {"real_only": False},
        {"real_only": False, "exact_adcode": first.adcode},
        {"real_only": False, "keyword": first.name[:3], "exact_adcode": first.adcode},
        {"real_only": False, "keyword": "不存在的分页检索词"},
    ]
    for filters in cases:
        expected = list(
            demo_session.scalars(
                service.stations.query(**filters)
                .with_only_columns(ChargingStation.id, maintain_column_froms=True)
                .order_by(ChargingStation.id)
            )
        )
        for page in (1, 2, 3):
            rows, total = service.stations.page(page=page, page_size=3, **filters)
            assert total == len(expected)
            assert [row.id for row in rows] == expected[(page - 1) * 3 : page * 3]
