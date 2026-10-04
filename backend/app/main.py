import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from app.api.health import router as health_router
from app.api.v1.amap import router as amap_router
from app.api.v1.analysis.accessibility import router as accessibility_router
from app.api.v1.analysis.planning import router as planning_router
from app.api.v1.analysis.routes import router as analysis_router
from app.api.v1.public_statistics import router as public_statistics_router
from app.api.v1.quality import router as quality_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.errors import failure, register_error_handlers
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings)

    def check_database():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            await run_in_threadpool(check_database)
            logging.getLogger("app").info(
                "startup database=connected environment=%s", settings.environment
            )
            yield
        except SQLAlchemyError:
            raise RuntimeError("无法连接数据库，请检查 DATABASE_URL 和 MySQL 服务") from None
        finally:
            engine.dispose()

    application = FastAPI(title=settings.app_name, version="0.1.0", debug=False, lifespan=lifespan)
    application.include_router(quality_router)
    application.include_router(public_statistics_router)
    application.include_router(analysis_router)
    application.include_router(accessibility_router)
    application.include_router(planning_router)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = create_session_factory(engine)
    register_error_handlers(application)

    @application.middleware("http")
    async def request_log(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger("app.errors").error(
                "request_id=%s type=%s", request.state.request_id, type(exc).__name__
            )
            response = failure(request, 500, "服务内部错误")
        response.headers["X-Request-ID"] = request.state.request_id
        logging.getLogger("app.requests").info(
            "%s %s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            request.state.request_id,
        )
        return response

    application.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health_router)
    application.include_router(v1_router)
    application.include_router(amap_router)
    return application


app = create_app()
