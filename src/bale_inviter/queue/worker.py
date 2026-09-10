"""Job worker.

Phase 2 executes CHECK_BALE_ACCOUNT only. DIRECT_INVITE, SEND_INVITE_LINK,
and CHECK_JOIN_STATUS stay without handlers.
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

JobHandler = Callable[[JobView], Awaitable[None]]


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
                "No handler registered in phase 2; only CHECK_BALE_ACCOUNT is enabled.",
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
        if job_type is not JobType.CHECK_BALE_ACCOUNT or self.interval_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_bale_call_at is not None:
            wait_for = self.interval_seconds - (now - self._last_bale_call_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
        self._last_bale_call_at = time.monotonic()


def build_account_check_worker(
    session: Session,
    adapter: BaleAdapter,
    settings: Settings | None = None,
    interval_seconds: int | None = None,
) -> JobWorker:
    cfg = settings or get_settings()
    queue = QueueService(session, cfg)
    service = AccountCheckService(session, adapter, queue)
    delay = cfg.invite_interval if interval_seconds is None else interval_seconds
    worker = JobWorker(queue, interval_seconds=delay)

    async def handle_check(job: JobView) -> None:
        if job.contact_id is None:
            raise ValueError("CHECK_BALE_ACCOUNT requires contact_id")
        await service.process_contact(job.contact_id)

    worker.register(JobType.CHECK_BALE_ACCOUNT, handle_check)
    return worker
