from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from bale_inviter.config import Settings, get_settings
from bale_inviter.database.models import Job, utcnow
from bale_inviter.database.repositories import JobRepository
from bale_inviter.domain.enums import JobStatus, JobType
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.models import DuplicateJobError, EnqueueRequest, JobView


class QueueService:
    """SQLite-backed job queue. Phase 1 stores and schedules jobs but never talks to Bale."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.jobs = JobRepository(session)

    def enqueue(self, request: EnqueueRequest) -> JobView:
        existing = self.jobs.find_active_by_key(request.unique_key)
        if existing is not None:
            log_event(
                logging.WARNING,
                "duplicate job rejected",
                operation=request.job_type.value,
                contact_id=request.contact_id,
                attempt_count=existing.attempts,
                error=f"active job id={existing.id} unique_key={request.unique_key}",
            )
            raise DuplicateJobError(
                f"Active job already exists for unique_key={request.unique_key} (id={existing.id})"
            )

        now = utcnow()
        delay = max(0, request.delay_seconds)
        max_attempts = request.max_attempts or self.settings.max_retries
        status = JobStatus.DELAYED if delay > 0 else JobStatus.PENDING
        job = Job(
            job_type=request.job_type,
            unique_key=request.unique_key,
            contact_id=request.contact_id,
            payload=request.payload or {},
            status=status,
            attempts=0,
            max_attempts=max_attempts,
            delay_seconds=delay,
            scheduled_at=now + timedelta(seconds=delay),
        )
        self.jobs.add(job)
        log_event(
            logging.INFO,
            f"job enqueued unique_key={request.unique_key} delay={delay}s",
            operation=request.job_type.value,
            contact_id=request.contact_id,
            attempt_count=0,
        )
        return self._to_view(job)

    def enqueue_for_contact(
        self,
        job_type: JobType,
        contact_id: int,
        payload: dict | None = None,
        delay_seconds: int = 0,
    ) -> JobView:
        return self.enqueue(
            EnqueueRequest(
                job_type=job_type,
                unique_key=f"{job_type.value}:{contact_id}",
                contact_id=contact_id,
                payload=payload,
                delay_seconds=delay_seconds,
            )
        )

    def claim_next(self) -> JobView | None:
        job = self.jobs.claim_due()
        if job is None:
            return None
        log_event(
            logging.INFO,
            f"job claimed id={job.id}",
            operation=job.job_type.value,
            contact_id=job.contact_id,
            attempt_count=job.attempts,
        )
        return self._to_view(job)

    def mark_success(self, job_id: int) -> JobView:
        job = self._require(job_id)
        job.status = JobStatus.COMPLETED
        job.completed_at = utcnow()
        job.last_error = None
        job.updated_at = utcnow()
        self.session.flush()
        log_event(
            logging.INFO,
            f"job completed id={job.id}",
            operation=job.job_type.value,
            contact_id=job.contact_id,
            attempt_count=job.attempts,
        )
        return self._to_view(job)

    def mark_failure(self, job_id: int, error: str, phone: str | None = None) -> JobView:
        job = self._require(job_id)
        now = utcnow()
        masked = mask_phone(phone) if phone else None
        safe_error = error
        job.last_error = safe_error
        job.updated_at = now
        if job.attempts < job.max_attempts:
            delay = job.delay_seconds or self.settings.job_retry_delay_seconds
            job.status = JobStatus.RETRYING
            job.scheduled_at = now + timedelta(seconds=delay)
            log_event(
                logging.WARNING,
                f"job will retry id={job.id} phone={masked or '-'} delay={delay}s",
                operation=job.job_type.value,
                contact_id=job.contact_id,
                attempt_count=job.attempts,
                error=safe_error,
            )
        else:
            job.status = JobStatus.FAILED
            job.completed_at = now
            log_event(
                logging.ERROR,
                f"job failed permanently id={job.id} phone={masked or '-'}",
                operation=job.job_type.value,
                contact_id=job.contact_id,
                attempt_count=job.attempts,
                error=safe_error,
            )
        self.session.flush()
        return self._to_view(job)

    def get_active(self, unique_key: str) -> JobView | None:
        job = self.jobs.find_active_by_key(unique_key)
        return None if job is None else self._to_view(job)

    def _require(self, job_id: int) -> Job:
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise KeyError(f"Job {job_id} not found")
        return job

    @staticmethod
    def _to_view(job: Job) -> JobView:
        return JobView(
            id=job.id,
            job_type=job.job_type,
            unique_key=job.unique_key,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            delay_seconds=job.delay_seconds,
            scheduled_at=job.scheduled_at,
            last_error=job.last_error,
            contact_id=job.contact_id,
            payload=job.payload or {},
        )
