from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from bale_inviter.database.session import create_db_engine, create_session_factory, get_session, init_db
from bale_inviter.reporting.service import ReportingService

router = APIRouter()
_engine = None
_session_factory = None


def _get_db() -> Session:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = init_db(create_db_engine())
        _session_factory = create_session_factory(_engine)
    yield from get_session(_session_factory)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "4", "platform": "telegram"}


@router.get("/report")
def report(session: Session = Depends(_get_db)) -> dict[str, int]:
    return ReportingService(session).as_dict()
