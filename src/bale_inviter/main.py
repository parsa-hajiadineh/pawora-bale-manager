from fastapi import FastAPI

from bale_inviter.config import get_settings
from bale_inviter.logging_setup import setup_logging
from bale_inviter.reporting.api import router as reporting_router

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir)

app = FastAPI(
    title="Bale Inviter",
    description="Phase 1 core: contact import, status, and job queue. No Bale operations.",
    version="0.1.0",
)
app.include_router(reporting_router)
