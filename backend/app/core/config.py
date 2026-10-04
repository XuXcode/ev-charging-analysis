from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_name: str = "湖南充电空间分析数据服务"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    database_url: SecretStr = SecretStr(
        "mysql+pymysql://ev_app:replace_me@127.0.0.1:3306/ev_charging?charset=utf8mb4"
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_recycle: int = Field(default=1800, ge=60)
    test_database_url: SecretStr | None = None
    amap_webservice_key: SecretStr | None = None

    @field_validator("database_url", "test_database_url")
    @classmethod
    def mysql_only(cls, value):
        if value is not None and make_url(value.get_secret_value()).drivername != "mysql+pymysql":
            raise ValueError("DATABASE_URL must use mysql+pymysql")
        return value

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
