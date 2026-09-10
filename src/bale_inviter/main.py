from fastapi import FastAPI

from bale_inviter.config import get_settings
from bale_inviter.logging_setup import setup_logging
from bale_inviter.reporting.api import router as reporting_router

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir)

app = FastAPI(
    title="Bale Inviter",
    description="Invite Excel contacts to a Telegram group by phone using a user session.",
    version="0.4.0",
)
app.include_router(reporting_router)
