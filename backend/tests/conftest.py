from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.db.seed import seed_demo
from app.db.session import create_db_engine, get_session
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings():
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.fail("请设置独立 MySQL TEST_DATABASE_URL")
    parsed = make_url(url.get_secret_value())
    if not parsed.database or not parsed.database.endswith("_test"):
        pytest.fail("测试数据库名必须以 _test 结尾")
    if parsed == make_url(settings.database_url.get_secret_value()):
        pytest.fail("测试数据库不得与应用数据库相同")
    return Settings(
        _env_file=None,
        database_url=url,
        test_database_url=url,
        cors_origins=settings.cors_origins,
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
def test_engine(test_settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = test_settings.database_url.get_secret_value()
    command.upgrade(config, "head")
    engine = create_db_engine(test_settings)
    yield engine
    engine.dispose()


@pytest.fixture
def session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    db_session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield db_session
    db_session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def demo_session(session):
    seed_demo(session)
    return session


@pytest.fixture
def client(demo_session, test_settings):
    application = create_app(test_settings.model_copy(deep=True))
    application.dependency_overrides[get_session] = lambda: demo_session
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
