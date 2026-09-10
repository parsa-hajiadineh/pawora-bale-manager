"""Worker skeleton.

Phase 1 does not execute CHECK_BALE_ACCOUNT, DIRECT_INVITE, SEND_INVITE_LINK,
or CHECK_JOIN_STATUS. Handlers will be registered in a later phase.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from bale_inviter.domain.enums import JobType
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.models import JobView
from bale_inviter.queue.service import QueueService

JobHandler = Callable[[JobView], Awaitable[None]]


class JobWorker:
    def __init__(self, queue: QueueService) -> None:
        self.queue = queue
        self._handlers: dict[JobType, JobHandler] = {}

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
                "No handler registered in phase 1; Bale operations are disabled.",
            )
            return True
        try:
            await handler(job)
            self.queue.mark_success(job.id)
        except Exception as exc:  # noqa: BLE001 - worker must isolate handler errors
            self.queue.mark_failure(job.id, str(exc))
        return True
