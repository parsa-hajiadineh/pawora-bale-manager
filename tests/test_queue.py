import asyncio

import pytest

from bale_inviter.adapters.bale import UnimplementedBaleAdapter
from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import JobStatus, JobType
from bale_inviter.queue.models import DuplicateJobError, EnqueueRequest
from bale_inviter.queue.service import QueueService


def _add_contact(session, phone_suffix: str = "1") -> Contact:
    contact = Contact(
        name=f"User {phone_suffix}",
        phone=f"0912000000{phone_suffix}",
        normalized_phone=f"+98912000000{phone_suffix}",
        is_valid=True,
        import_fingerprint=f"fp-{phone_suffix}",
    )
    session.add(contact)
    session.flush()
    return contact


def test_enqueue_and_claim(session, settings) -> None:
    contact = _add_contact(session, "1")
    queue = QueueService(session, settings)
    view = queue.enqueue_for_contact(JobType.CHECK_BALE_ACCOUNT, contact_id=contact.id)
    assert view.status is JobStatus.PENDING
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING
    assert claimed.attempts == 1


def test_duplicate_active_job_is_rejected(session, settings) -> None:
    contact = _add_contact(session, "9")
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact_id=contact.id)
    with pytest.raises(DuplicateJobError):
        queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact_id=contact.id)


def test_completed_job_can_be_enqueued_again(session, settings) -> None:
    contact = _add_contact(session, "4")
    queue = QueueService(session, settings)
    first = queue.enqueue_for_contact(JobType.SEND_INVITE_LINK, contact_id=contact.id)
    claimed = queue.claim_next()
    assert claimed is not None
    queue.mark_success(claimed.id)
    second = queue.enqueue_for_contact(JobType.SEND_INVITE_LINK, contact_id=contact.id)
    assert second.id != first.id


def test_retry_then_permanent_failure(session, settings) -> None:
    contact = _add_contact(session, "7")
    queue = QueueService(session, settings)
    queue.enqueue(
        EnqueueRequest(
            job_type=JobType.CHECK_JOIN_STATUS,
            unique_key=f"{JobType.CHECK_JOIN_STATUS.value}:{contact.id}",
            contact_id=contact.id,
            max_attempts=2,
        )
    )
    first = queue.claim_next()
    assert first is not None
    retried = queue.mark_failure(first.id, "temporary error")
    assert retried.status is JobStatus.RETRYING
    second = queue.claim_next()
    assert second is not None
    failed = queue.mark_failure(second.id, "still failing")
    assert failed.status is JobStatus.FAILED
    assert queue.claim_next() is None


def test_mark_failure_uses_explicit_delay(session, settings) -> None:
    contact = _add_contact(session, "8")
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact.id)
    claimed = queue.claim_next()
    assert claimed is not None
    retried = queue.mark_failure(claimed.id, "flood", delay_seconds=0)
    assert retried.status is JobStatus.RETRYING
    assert queue.claim_next() is not None


def test_delayed_job_is_not_claimed(session, settings) -> None:
    queue = QueueService(session, settings)
    queue.enqueue(
        EnqueueRequest(
            job_type=JobType.CHECK_BALE_ACCOUNT,
            unique_key="CHECK_BALE_ACCOUNT:delay",
            delay_seconds=3600,
        )
    )
    assert queue.claim_next() is None


def test_phase1_adapter_does_not_call_bale() -> None:
    adapter = UnimplementedBaleAdapter()
    with pytest.raises(NotImplementedError):
        asyncio.run(adapter.direct_invite("+989121234567", "group"))
