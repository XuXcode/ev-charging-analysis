"""Verify the running API contract with read-only requests; omit credentials and raw POIs."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def request(path, expected=200):
    try:
        with urlopen(BASE + path, timeout=15) as response:
            status, payload = response.status, json.load(response)
    except HTTPError as failure:
        status, payload = failure.code, json.load(failure)
    assert status == expected, (path, status, expected)
    return payload


def data(path):
    return request("/api/v1" + path)["data"]


def main():
    snapshot = data("/analysis/latest?classification=public_candidate")
    all_snapshot = data("/analysis/latest")
    metadata = snapshot["metadata"]
    stations = data("/stations?page_size=1")
    public = data("/stations?classification=public_candidate&page_size=1")
    reviews = data("/stations?needs_review=true&page_size=1")
    zero = data("/analysis/latest?classification=personal&review_status=confirmed")
    province = data("/analysis/boundaries?parent=430000")
    districts = sum(
        len(data(f"/analysis/boundaries?parent={city['code']}")["features"])
        for city in snapshot["cities"]
    )
    search = data(
        "/stations?keyword=B0J29G1CD0&classification=public_candidate&page_size=8"
    )
    assert len(snapshot["cities"]) == len(province["features"]) == 14
    assert len(snapshot["districts"]) == districts == 122
    assert stations["total"] == metadata["datasetStationCount"] == 12601
    assert public["total"] == metadata["stationCount"] == 11720
    assert reviews["total"] == 875
    assert zero["province"]["count"] == zero["province"]["coveragePercent"] == 0
    assert search["total"] == 1 and search["items"][0]["adcode"] == "430102"
    assert not snapshot["stale"]
    assert "frozenInputs" not in snapshot and "layers" not in snapshot
    assert len(metadata["qualityRunIds"]) == 2
    assert len(metadata["frozenInputHash"]) == 64
    for region in [snapshot["province"], *snapshot["cities"], *snapshot["districts"]]:
        assert (
            abs(
                region["coveredAreaKm2"]
                + region["uncoveredAreaKm2"]
                - region["areaKm2"]
            )
            < 1e-6
        )
        assert 0 <= region["coveragePercent"] <= 100
    for path, expected in [
        ("/api/v1/stations?city=430100&adcode=431002", 422),
        ("/api/v1/stations?bbox=113,29,112,28", 422),
        ("/api/v1/analysis/latest?classification=invented", 422),
        ("/api/v1/analysis/boundaries?parent=439900", 404),
    ]:
        request(path, expected)
    schema = request("/openapi.json")
    for path in [
        "/api/v1/stations",
        "/api/v1/analysis/latest",
        "/api/v1/analysis/boundaries",
        "/api/v1/quality/pois",
    ]:
        assert schema["paths"][path]["get"].get("description")
    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "readOnly": True,
        "datasetCount": stations["total"],
        "publicCandidateCount": public["total"],
        "reviewClues": reviews["total"],
        "cities": 14,
        "districts": districts,
        "snapshotId": snapshot["snapshotId"],
        "algorithmVersion": metadata["algorithmVersion"],
        "stale": snapshot["stale"],
        "qualityRunIds": metadata["qualityRunIds"],
        "frozenInputHash": metadata["frozenInputHash"],
        "assignment": metadata.get("assignment"),
        "assignmentScope": "public_candidate",
        "allClassificationCounts": all_snapshot["metadata"]["classificationCounts"],
        "allAssignment": all_snapshot["metadata"].get("assignment"),
        "checks": [
            "count and scope agreement",
            "14/122 real boundaries",
            "137 area complements",
            "zero scope preserved",
            "real POI ID search",
            "no frozen inputs or unused layers in latest API",
            "invalid scope and bbox rejected",
            "missing boundaries explicit 404",
            "live OpenAPI descriptions",
        ],
    }
    target = ROOT / "docs/reports" / "DEEP_RUNTIME_AUDIT.json"
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"assignment", "allAssignment"}
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
