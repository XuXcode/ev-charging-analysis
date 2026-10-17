"""Explicit, bounded interactive queries; GET policy and POST plan never call AMap."""

from fastapi import APIRouter, Query, Request

from app.api.dependencies import SessionDep
from app.schemas.common import APIResponse
from app.schemas.custom_accessibility import CustomQuery
from app.services.analysis import custom_accessibility as service

router = APIRouter(prefix="/api/v1/analysis/accessibility/custom", tags=["自定义地点驾车查询"])


@router.get("/policy", response_model=APIResponse[dict])
def policy(session: SessionDep, request: Request):
    return APIResponse(data=service.policy(session, request.app.state.settings))


@router.post("/plan", response_model=APIResponse[dict])
def plan(body: CustomQuery, session: SessionDep, request: Request):
    return APIResponse(data=service.plan(session, body, request.app.state.settings))


@router.post("/routes", response_model=APIResponse[dict])
def routes(body: CustomQuery, session: SessionDep, request: Request):
    return APIResponse(data=service.execute(session, body, request.app.state.settings))


@router.get("/places", response_model=APIResponse[dict])
def places(
    session: SessionDep, request: Request, keyword: str = Query(min_length=2, max_length=80)
):
    return APIResponse(data=service.places(session, request.app.state.settings, keyword.strip()))
