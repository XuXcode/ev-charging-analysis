"""python -m app.services.governance_job; does not collect or delete POIs."""

import json

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.services.governance import govern_pois


def main():
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            with session.begin():
                result = govern_pois(session)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
