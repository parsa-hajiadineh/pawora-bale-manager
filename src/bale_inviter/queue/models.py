from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bale_inviter.domain.enums import JobStatus, JobType


class DuplicateJobError(ValueError):
    pass


@dataclass(slots=True)
class EnqueueRequest:
    job_type: JobType
    unique_key: str
    contact_id: int | None = None
    payload: dict | None = None
    delay_seconds: int = 0
    max_attempts: int | None = None


@dataclass(slots=True)
class JobView:
    id: int
    job_type: JobType
    unique_key: str
    status: JobStatus
    attempts: int
    max_attempts: int
    delay_seconds: int
    scheduled_at: datetime
    last_error: str | None = None
    contact_id: int | None = None
    payload: dict = field(default_factory=dict)
