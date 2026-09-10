from pathlib import Path

import pytest
from bale_inviter.config import Settings
from bale_inviter.database.models import Base
from bale_inviter.database.session import create_db_engine, create_session_factory


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        max_retries=3,
        job_retry_delay_seconds=0,
        log_level="INFO",
        log_dir=str(tmp_path / "logs"),
    )


@pytest.fixture
def session(settings: Settings):
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    db = factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()
        engine.dispose()
