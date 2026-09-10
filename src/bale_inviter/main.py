from fastapi import FastAPI

from bale_inviter.config import get_settings
from bale_inviter.logging_setup import setup_logging
from bale_inviter.reporting.api import router as reporting_router

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir)

app = FastAPI(
    title="Bale Inviter",
    description="Phase 2: contact import, status, job queue, and Bale account checks. No invites or private messages.",
    version="0.2.0",
)
app.include_router(reporting_router)
