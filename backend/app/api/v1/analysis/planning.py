"""Planning evidence APIs. This router never initiates provider requests."""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.models import AnalysisBoundary, ChargingStation, PlanningDataset, PlanningRun, PoiQuality
from app.schemas.common import APIResponse
from app.schemas.planning import DatasetImport, DemandPreviewRequest, OptimizationRequest
from app.services.analysis.candidates import filter_candidates
from app.services.analysis.demand import prepare
from app.services.analysis.od_matrix import cached_matrix, nearby_indices, plan
from app.services.analysis.optimization import greedy, mclp
from app.services.analysis.road import distance_m, frozen_digest

router = APIRouter(prefix="/api/v1/analysis/planning", tags=["需求与选址基座"])


@router.post("/demand-preview", response_model=APIResponse[dict])
def demand_preview(payload: DemandPreviewRequest, session: SessionDep):
    dataset = session.get(PlanningDataset, payload.datasetId)
    if dataset is None or dataset.kind != "demand":
        raise HTTPException(404, "真实需求数据集尚未接入")
    try:
        result = prepare(dataset.records, payload.weights)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return APIResponse(
        data={
            **result,
            "datasetId": dataset.id,
            "datasetHash": dataset.content_hash,
            "batch": dataset.metadata_json["batch"],
            "completeCount": sum(n["complete"] for n in result["nodes"]),
        }
    )


@router.post("/datasets", response_model=APIResponse[dict])
def import_dataset(payload: DatasetImport, session: SessionDep):
    data = payload.model_dump(mode="json")
    identity = frozen_digest(data)
    previous = session.scalar(
        select(PlanningDataset.id).where(PlanningDataset.content_hash == identity)
    )
    if previous:
        return APIResponse(data={"id": previous, "reused": True})
    row = PlanningDataset(
        id=uuid.uuid4().hex,
        kind=payload.kind,
        name=payload.name,
        content_hash=identity,
        metadata_json={k: v for k, v in data.items() if k != "records"},
        records=data["records"],
    )
    session.add(row)
    session.commit()
    return APIResponse(
        data={
            "id": row.id,
            "reused": False,
            "recordCount": len(row.records),
            "contentHash": identity,
        }
    )


@router.get("/datasets", response_model=APIResponse[dict])
def datasets(session: SessionDep):
    rows = session.execute(
        select(
            PlanningDataset.id,
            PlanningDataset.kind,
            PlanningDataset.name,
            PlanningDataset.content_hash,
            PlanningDataset.metadata_json,
            PlanningDataset.created_at,
        ).order_by(PlanningDataset.created_at.desc())
    ).all()
    return APIResponse(
        data={
            "items": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "name": r.name,
                    "contentHash": r.content_hash,
                    "metadata": r.metadata_json,
                    "createdAt": r.created_at.isoformat() + "Z",
                }
                for r in rows
            ],
            "notice": "来源字段是提交者提供的证据记录，导入校验不等于独立认证数据真实性。",
        }
    )


@router.get("/runs/{run_id}", response_model=APIResponse[dict])
def read_run(run_id: str, session: SessionDep):
    row = session.get(PlanningRun, run_id)
    if row is None:
        raise HTTPException(404, "优化方案不存在")
    return APIResponse(
        data={
            "id": row.id,
            "inputHash": row.input_hash,
            "parameters": row.parameters,
            "result": row.result,
            "createdAt": row.created_at.isoformat() + "Z",
        }
    )


def existing_records(session):
    stations = session.execute(
        select(
            ChargingStation.poi_id,
            ChargingStation.name,
            ChargingStation.longitude,
            ChargingStation.latitude,
            ChargingStation.collected_at,
            PoiQuality.run_id,
        )
        .join(PoiQuality, PoiQuality.station_id == ChargingStation.id)
        .where(ChargingStation.source == "amap", PoiQuality.classification == "public_candidate")
        .order_by(ChargingStation.poi_id)
    ).all()
    return [
        {
            "id": r.poi_id,
            "name": r.name,
            "position": [float(r.longitude), float(r.latitude)],
            "collectedAt": r.collected_at.isoformat() + "Z",
            "batch": r.run_id,
        }
        for r in stations
    ]


@router.post("/optimization", response_model=APIResponse[dict])
def optimize(payload: OptimizationRequest, session: SessionDep):
    demand = session.get(PlanningDataset, payload.demandDatasetId)
    candidates = session.get(PlanningDataset, payload.candidateDatasetId)
    boundary = session.get(AnalysisBoundary, payload.scopeCode)
    if demand is None or candidates is None or boundary is None:
        raise HTTPException(404, "真实需求、候选数据集或行政边界尚未接入")
    if demand.kind != "demand" or candidates.kind != "candidates":
        raise HTTPException(422, "输入数据集类型不匹配")
    if len(demand.records) > 500 or len(candidates.records) > 300:
        raise HTTPException(422, "首版同步求解限500需求点、300候选设施，请先按行政区域分批")
    from shapely import STRtree
    from shapely.geometry import Point, shape

    polygon = shape(boundary.geometry)
    origins_raw = [r for r in demand.records if polygon.covers(Point(r["position"]))]
    existing = existing_records(session)
    try:
        demand_result = prepare(origins_raw, payload.weights)
        candidate_result = filter_candidates(
            candidates.records,
            boundary.geometry,
            existing,
            min_existing_distance_m=payload.minExistingDistanceM,
            dedup_distance_m=payload.dedupDistanceM,
        )
        origins, sites = demand_result["nodes"], candidate_result["candidates"]
        edges = [
            {
                "originId": o["id"],
                "destinationId": c["id"],
                "status": "ok",
                "straightDistanceM": distance_m(o["position"], c["position"]),
            }
            for o in origins
            for c in sites
        ]
        station_tree = STRtree([Point(s["position"]) for s in existing])
        baseline = [
            o["id"]
            for o in origins
            if payload.metric == "straightDistanceM"
            and any(
                distance_m(o["position"], existing[int(i)]["position"]) <= payload.threshold
                for i in nearby_indices(station_tree, o["position"], payload.threshold)
            )
        ]
        baseline_od = None
        if payload.metric == "durationSeconds":
            edges = cached_matrix(session, origins, sites)
            baseline_od = plan(session, origins, existing, nearest=3)
            observed_origins = {e["originId"] for e in baseline_od["edges"]}
            if any(
                e["status"] == "missing" for e in edges + baseline_od["edges"]
            ) or observed_origins != {o["id"] for o in origins}:
                missing = {
                    e["cacheKey"] for e in edges + baseline_od["edges"] if e["status"] == "missing"
                }
                raise HTTPException(
                    409,
                    {
                        "message": "道路矩阵未完整，不生成优化方案；不发起路线请求",
                        "missingUniqueOD": len(missing),
                        "apiCalls": 0,
                    },
                )
            baseline = sorted(
                {
                    e["originId"]
                    for e in baseline_od["edges"]
                    if e["status"] == "ok" and e["durationSeconds"] <= payload.threshold
                }
            )
        problem = {
            "origins": origins,
            "candidates": sites,
            "candidateExclusions": candidate_result["excluded"],
            "demandNormalization": {
                "version": demand_result["version"],
                "weights": demand_result["weights"],
                "limits": demand_result["limits"],
                "unit": demand_result["unit"],
            },
            "edges": edges,
            "baselineCovered": baseline,
            "n": payload.n,
            "metric": payload.metric,
            "threshold": payload.threshold,
        }
        result = (
            greedy(problem)
            if payload.algorithm == "greedy"
            else mclp(problem, time_limit=payload.timeLimitSeconds)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    inputs = {
        "problem": problem,
        "demandDatasetHash": demand.content_hash,
        "candidateDatasetHash": candidates.content_hash,
        "boundaryHash": boundary.content_hash,
        "existingStations": existing,
        "normalization": demand_result,
        "candidateDecisions": candidate_result,
        "baselineOD": baseline_od,
    }
    result.update(
        {
            "recommended": [c for c in sites if c["id"] in result["selectedIds"]],
            "candidates": sites,
            "candidateExclusions": candidate_result["excluded"],
            "demandNormalization": problem["demandNormalization"],
            "existingStations": [s for s in existing if polygon.covers(Point(s["position"]))],
            "origins": origins,
            "averageRoadTimeBefore": None,
            "averageRoadTimeAfter": None,
            "dataBatches": [demand.metadata_json["batch"], candidates.metadata_json["batch"]],
            "metricNotice": "GCJ-02坐标球面直线距离近似，不是驾车服务时间或法定人口覆盖。",
        }
    )
    if baseline_od is not None:

        def route_mean(edge_rows):
            nearest = {}
            for edge in edge_rows:
                if edge["status"] == "ok":
                    nearest[edge["originId"]] = min(
                        nearest.get(edge["originId"], float("inf")), edge["durationSeconds"]
                    )
            return {
                "seconds": sum(nearest.values()) / len(nearest) if nearest else None,
                "validOriginCount": len(nearest),
            }

        result["averageRoadTimeBefore"] = route_mean(baseline_od["edges"])
        result["averageRoadTimeAfter"] = route_mean(
            baseline_od["edges"] + [e for e in edges if e["destinationId"] in result["selectedIds"]]
        )
        result["metricNotice"] = (
            "真实缓存驾车观测；现状筛选20km内最近3个公共候选站，非全站最短时间。需求覆盖按导入权重计，非面积或人口覆盖。"
        )
    row = PlanningRun(
        id=uuid.uuid4().hex,
        algorithm_version=result["algorithmVersion"],
        input_hash=frozen_digest(inputs),
        parameters=payload.model_dump(),
        inputs=inputs,
        result=result,
    )
    session.add(row)
    session.commit()
    return read_run(row.id, session)


@router.post("/od-estimate", response_model=APIResponse[dict])
def estimate(payload: OptimizationRequest, session: SessionDep):
    demand = session.get(PlanningDataset, payload.demandDatasetId)
    candidates = session.get(PlanningDataset, payload.candidateDatasetId)
    if (
        demand is None
        or candidates is None
        or demand.kind != "demand"
        or candidates.kind != "candidates"
    ):
        raise HTTPException(404, "需先导入真实需求和真实候选设施数据")
    if len(demand.records) > 500 or len(candidates.records) > 300:
        raise HTTPException(422, "先按行政区域分批，单次限500需求点和300候选")
    from shapely.geometry import Point, shape

    boundary = session.get(AnalysisBoundary, payload.scopeCode)
    if boundary is None:
        raise HTTPException(404, "所选区域边界尚未接入")
    polygon = shape(boundary.geometry)
    origins = [r for r in demand.records if polygon.covers(Point(r["position"]))]
    existing = existing_records(session)
    try:
        sites = filter_candidates(
            candidates.records,
            boundary.geometry,
            existing,
            min_existing_distance_m=payload.minExistingDistanceM,
            dedup_distance_m=payload.dedupDistanceM,
        )["candidates"]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    candidate_edges = cached_matrix(session, origins, sites)
    baseline = plan(session, origins, existing, nearest=3)
    edges = candidate_edges + baseline["edges"]
    misses = {e["cacheKey"] for e in edges if e["status"] == "missing"}
    return APIResponse(
        data={
            "scopeCode": payload.scopeCode,
            "originCount": len(origins),
            "candidateCount": len(sites),
            "pairCount": len(edges),
            "candidateUniqueOD": len({e["cacheKey"] for e in candidate_edges}),
            "baselineUniqueOD": baseline["uniqueOD"],
            "uniqueOD": len({e["cacheKey"] for e in edges}),
            "estimatedCalls": len(misses),
            "maxAttempts": 3 * len(misses),
            "originsWithoutExistingCandidates": baseline["originsWithoutCandidates"],
            "apiCalls": 0,
            "notice": "包含所选区域筛选后候选完整矩阵及20km内最近3个原有站基线；只读缓存，实际采样需单独确认。",
        }
    )
