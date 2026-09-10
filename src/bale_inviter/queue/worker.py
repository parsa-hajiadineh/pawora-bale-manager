"""Job worker.

Phase 3 executes CHECK_BALE_ACCOUNT, DIRECT_INVITE, SEND_INVITE_LINK,
and CHECK_JOIN_STATUS with a shared rate limit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy.orm import Session

from bale_inviter.adapters.bale import BaleAdapter, RetryableBaleError
from bale_inviter.config import Settings, get_settings
from bale_inviter.domain.enums import JobType
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.models import JobView
from bale_inviter.queue.service import QueueService
from bale_inviter.services.account_check import AccountCheckService
from bale_inviter.services.invite import InviteService

JobHandler = Callable[[JobView], Awaitable[None]]

RATE_LIMITED_JOBS = {
    JobType.CHECK_BALE_ACCOUNT,
    JobType.DIRECT_INVITE,
    JobType.SEND_INVITE_LINK,
    JobType.CHECK_JOIN_STATUS,
}


class JobWorker:
    def __init__(self, queue: QueueService, interval_seconds: int = 0) -> None:
        self.queue = queue
        self.interval_seconds = max(0, interval_seconds)
        self._handlers: dict[JobType, JobHandler] = {}
        self._last_bale_call_at: float | None = None

    def register(self, job_type: JobType, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def process_one(self) -> bool:
        job = self.queue.claim_next()
        if job is None:
            return False
        handler = self._handlers.get(job.job_type)
        if handler is None:
            log_event(
                logging.WARNING,
                f"no handler registered; job left unexecuted id={job.id}",
                operation=job.job_type.value,
                contact_id=job.contact_id,
                attempt_count=job.attempts,
            )
            self.queue.mark_failure(
                job.id,
                "No handler registered for this job type.",
                retry=False,
            )
            return True
        try:
            await self._respect_interval(job.job_type)
            await handler(job)
            self.queue.mark_success(job.id)
        except RetryableBaleError as exc:
            self.queue.mark_failure(job.id, str(exc))
        except Exception as exc:  # noqa: BLE001 - worker must isolate handler errors
            self.queue.mark_failure(job.id, str(exc))
        return True

    async def _respect_interval(self, job_type: JobType) -> None:
        if job_type not in RATE_LIMITED_JOBS or self.interval_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_bale_call_at is not None:
            wait_for = self.interval_seconds - (now - self._last_bale_call_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
        self._last_bale_call_at = time.monotonic()


def build_worker(
    session: Session,
    adapter: BaleAdapter,
    settings: Settings | None = None,
    interval_seconds: int | None = None,
) -> JobWorker:
    cfg = settings or get_settings()
    queue = QueueService(session, cfg)
    checks = AccountCheckService(session, adapter, queue)
    invites = InviteService(session, adapter, queue, cfg)
    delay = cfg.invite_interval if interval_seconds is None else interval_seconds
    worker = JobWorker(queue, interval_seconds=delay)

    async def handle_check(job: JobView) -> None:
        if job.contact_id is None:
            raise ValueError("CHECK_BALE_ACCOUNT requires contact_id")
        await checks.process_contact(job.contact_id)

    async def handle_direct_invite(job: JobView) -> None:
        if job.contact_id is None:
            raise ValueError("DIRECT_INVITE requires contact_id")
        await invites.process_direct_invite(job.contact_id)

    async def handle_invite_link(job: JobView) -> None:
        if job.contact_id is None:
            raise ValueError("SEND_INVITE_LINK requires contact_id")
        await invites.process_invite_link(job.contact_id)

    async def handle_join(job: JobView) -> None:
        if job.contact_id is None:
            raise ValueError("CHECK_JOIN_STATUS requires contact_id")
        await invites.process_join_check(job.contact_id)

    worker.register(JobType.CHECK_BALE_ACCOUNT, handle_check)
    worker.register(JobType.DIRECT_INVITE, handle_direct_invite)
    worker.register(JobType.SEND_INVITE_LINK, handle_invite_link)
    worker.register(JobType.CHECK_JOIN_STATUS, handle_join)
    return worker


build_account_check_worker = build_worker
