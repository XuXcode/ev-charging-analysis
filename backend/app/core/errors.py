import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger("app.errors")


def failure(request: Request, code: int, message: str, data=None) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": data if data is not None else {}},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


def register_error_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return failure(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(map(str, item["loc"])), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        return failure(request, 422, "请求参数不合法", errors)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error(
            "database request_id=%s type=%s",
            getattr(request.state, "request_id", ""),
            type(exc).__name__,
        )
        return failure(request, 503, "数据库暂时不可用")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error(
            "unexpected request_id=%s type=%s",
            getattr(request.state, "request_id", ""),
            type(exc).__name__,
        )
        return failure(request, 500, "服务内部错误")
