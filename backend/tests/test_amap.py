import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.models import ChargingStation


def fake_provider(monkeypatch, client, handler):
    original_client = httpx.Client
    monkeypatch.setattr(
        "app.services.amap.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.state.settings.amap_webservice_key = SecretStr("unit-test-key")


def test_amap_requires_key_no_mock_fallback(client):
    assert client.get("/api/v1/amap/status").json()["data"] == {"configured": False}
    response = client.get("/api/v1/amap/stations?city=430100")
    assert response.status_code == 503 and response.json()["data"] == {}


def test_amap_mapping_is_not_a_statistical_total(client, demo_session, monkeypatch):
    def handler(request):
        assert request.url.host == "restapi.amap.com"
        assert request.url.params["region"] == "430100"
        assert request.url.params["city_limit"] == "true"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "count": "999999",
                "pois": [
                    {
                        "id": "provider-test-id",
                        "name": "测试响应地点",
                        "location": "112.93,28.22",
                        "adcode": "430102",
                        "address": "字段映射测试",
                    },
                    {
                        "id": "outside-city",
                        "name": "区外测试",
                        "location": "113,27",
                        "adcode": "430202",
                    },
                    {"id": "invalid", "name": "无效坐标", "location": "nan,28", "adcode": "430102"},
                ],
            },
        )

    fake_provider(monkeypatch, client, handler)
    before = demo_session.scalar(select(func.count()).select_from(ChargingStation))
    response = client.get("/api/v1/amap/stations?city=430100")
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["returnedCount"] == 1 and result["skippedCount"] == 2
    assert "total" not in result
    assert result["items"][0]["piles"] is None
    assert result["items"][0]["position"] == [112.93, 28.22]
    assert not result["items"][0]["simulated"]
    assert demo_session.scalar(select(func.count()).select_from(ChargingStation)) == before


@pytest.mark.parametrize(
    "query", ["city=430000", "city=430100&page=9", "city=430100&page_size=26", "city=123"]
)
def test_amap_bounds(client, monkeypatch, query):
    fake_provider(monkeypatch, client, lambda request: pytest.fail("无效参数不应发送请求"))
    assert client.get("/api/v1/amap/stations?" + query).status_code == 422


@pytest.mark.parametrize(("mode", "status"), [("vendor", 502), ("timeout", 504), ("format", 502)])
def test_amap_failure_redaction(client, monkeypatch, mode, status):
    def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("private key and URL", request=request)
        return httpx.Response(
            200, json={"status": "0", "info": "private vendor detail"} if mode == "vendor" else []
        )

    fake_provider(monkeypatch, client, handler)
    response = client.get("/api/v1/amap/stations?city=430100")
    assert response.status_code == status
    assert "unit-test-key" not in response.text and "private" not in response.text
