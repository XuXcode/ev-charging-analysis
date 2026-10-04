from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services.data import DataService

SessionDep = Annotated[Session, Depends(get_session)]


def get_data_service(session: SessionDep) -> DataService:
    return DataService(session)


DataServiceDep = Annotated[DataService, Depends(get_data_service)]
