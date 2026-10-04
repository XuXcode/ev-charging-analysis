from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import SessionDep
from app.schemas.common import APIResponse, ErrorResponse

router = APIRouter(tags=["健康检查"])


@router.get(
    "/api/health", response_model=APIResponse[dict], responses={503: {"model": ErrorResponse}}
)
def health(session: SessionDep):
    session.execute(text("SELECT 1"))
    return APIResponse(data={"status": "ok", "database": "connected"})
