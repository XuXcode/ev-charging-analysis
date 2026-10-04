from logging.config import dictConfig


def configure_logging(level: str):
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
            },
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )
