from types import SimpleNamespace

import pytest

from app.services.analysis.road import aggregate, distance_m, od_request, parse_route


def test_frozen_digest_tolerates_mysql_float_representation_not_input_changes():
    from app.services.analysis.road import frozen_digest

    assert frozen_digest({"v": 100.0, "x": 112.123456789012}) == frozen_digest(
        {"x": 112.12345678901, "v": 100}
    )
    assert frozen_digest({"x": 112.12345678}) != frozen_digest({"x": 112.12345680})


def test_real_route_parser_never_invents_time_or_distance():
    assert parse_route({"status": "1", "route": {"paths": []}}) == {"status": "no_route"}
    assert parse_route({"status": "1", "route": []})["status"] == "invalid_response"
    assert parse_route({"status": "0", "infocode": "10003", "info": "secret"}) == {
        "status": "provider_error",
        "code": "10003",
    }
    assert (
        parse_route({"status": "1", "route": {"paths": [{"duration": "NaN", "distance": "1"}]}})[
            "status"
        ]
        == "invalid_response"
    )
    assert parse_route(
        {
            "status": "1",
            "route": {
                "paths": [
                    {"duration": "301", "distance": "1700"},
                    {"duration": "299", "distance": "1800"},
                ]
            },
        }
    ) == {"status": "ok", "durationSeconds": 299.0, "distanceM": 1800.0}


def test_od_identity_preserves_direction_and_rounding():
    a, b = [112.1234567, 28.2], [112.2, 28.3]
    assert od_request(a, b)["origin"] == "112.123457,28.200000"
    assert od_request(a, b) != od_request(b, a)
    assert distance_m(a, a) == 0
    assert 0 < distance_m(a, b) < 20000
    with pytest.raises(ValueError):
        od_request([float("inf"), 28], b)


def test_partial_od_is_unknown_not_false_and_denominators_explicit():
    run = SimpleNamespace(
        inputs={
            "origins": [{"adcode": "430102"}, {"adcode": "430103"}, {"adcode": "430104"}],
            "stations": [{"qualityBatch": "evidence"}],
            "tasks": [
                {"adcode": "430102", "cacheKey": "a", "poiId": "A"},
                {"adcode": "430103", "cacheKey": "b", "poiId": "B"},
                {"adcode": "430103", "cacheKey": "c", "poiId": "C"},
            ],
        },
        progress={
            "a": {"status": "ok", "durationSeconds": 300, "distanceM": 2000},
            "b": {"status": "ok", "durationSeconds": 200, "distanceM": 1500},
        },
    )
    result = aggregate(run)
    assert result["resolvedOriginCount"] == 1
    assert result["thresholdPercent"]["5"] == 100
    assert result["meanNearestDurationSeconds"] == 300
    assert result["regions"][1]["thresholdReached"]["5"] is None
    assert result["regions"][2]["durationSeconds"] is None
    assert result["ratioDenominator"] == 1


def test_quota_reservation_resume_and_cross_run_cache(session):
    import uuid

    import httpx

    from app.models import RoadAccessibilityRun
    from app.services.analysis.job import digest
    from app.services.analysis.road import ENDPOINT, VERSION, execute, frozen_digest

    tasks = []
    for number in [1, 2]:
        request = od_request([112, 28], [112 + number * 0.001, 28])
        tasks.append(
            {
                "adcode": "430102",
                "cacheKey": digest({"endpoint": ENDPOINT, "coordinateSystem": "GCJ-02", **request}),
                "poiId": str(number),
                "request": request,
            }
        )
    inputs = {
        "origins": [{"adcode": "430102"}],
        "tasks": tasks,
        "stations": [{"qualityBatch": "test-only"}],
    }

    def new_run():
        run = RoadAccessibilityRun(
            id=uuid.uuid4().hex,
            status="prepared",
            algorithm_version=VERSION,
            input_hash=frozen_digest(inputs),
            inputs=inputs,
            parameters={
                "maxCalls": 1,
                "maxAttemptsPerOD": 3,
                "cacheTtlDays": 7,
                "minimumIntervalSeconds": 0,
            },
            progress={},
            result={},
            api_calls=0,
            cache_hits=0,
        )
        session.add(run)
        session.flush()
        return run

    calls = []

    def response(request):
        calls.append(request.url.params["destination"])
        return httpx.Response(
            200, json={"status": "1", "route": {"paths": [{"duration": "60", "distance": "500"}]}}
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        first = new_run()
        execute(session, first, "test-only-key", client)
        assert first.api_calls == 1 and first.status == "quota_stopped"
        execute(session, first, "test-only-key", client)
        assert len(calls) == 1  # A restart must not reset quota or repeat completed OD.
        second = new_run()
        execute(session, second, "test-only-key", client)
        assert second.cache_hits == 1 and second.api_calls == 1
        assert second.status == "completed" and len(calls) == 2
