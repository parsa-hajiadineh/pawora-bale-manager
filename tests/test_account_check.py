import asyncio

import pytest

from bale_inviter.adapters.bale import BaleAccountCheckResult, RetryableBaleError, SharedContactUpdate
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import BaleAccountStatus, JobStatus, JobType
from bale_inviter.queue.models import DuplicateJobError
from bale_inviter.queue.service import QueueService
from bale_inviter.queue.worker import build_account_check_worker
from bale_inviter.services.account_check import AccountCheckService


def _add_contact(session, suffix: str, user_id: str | None = None) -> Contact:
    contact = Contact(
        name=f"User {suffix}",
        phone=f"0912000000{suffix}",
        normalized_phone=f"+98912000000{suffix}",
        is_valid=True,
        import_fingerprint=f"fp-check-{suffix}",
        bale_user_id=user_id,
    )
    session.add(contact)
    session.flush()
    return contact


def test_check_with_user_id_sets_has_account(session, settings) -> None:
    contact = _add_contact(session, "1", user_id="1001")
    adapter = FakeBaleAdapter(
        accounts={
            contact.normalized_phone: BaleAccountCheckResult(
                status=BaleAccountStatus.HAS_ACCOUNT,
                bale_user_id="1001",
                detail="fake",
            )
        }
    )
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    result = asyncio.run(service.process_contact(contact.id))
    assert result.status is BaleAccountStatus.HAS_ACCOUNT
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT
    assert contact.bale_user_id == "1001"
    assert contact.error_message is None


def test_check_without_user_id_stays_unknown(session, settings) -> None:
    contact = _add_contact(session, "2")
    adapter = FakeBaleAdapter()
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    result = asyncio.run(service.process_contact(contact.id))
    assert result.detail == "phone_lookup_unsupported"
    assert contact.bale_account_status is BaleAccountStatus.UNKNOWN
    assert contact.error_message == "phone_lookup_unsupported"


def test_enqueue_skips_duplicate_active_jobs(session, settings) -> None:
    contact = _add_contact(session, "3", user_id="3")
    adapter = FakeBaleAdapter()
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    first = service.enqueue_pending()
    assert first.queued == 1
    with pytest.raises(DuplicateJobError):
        QueueService(session, settings).enqueue_for_contact(JobType.CHECK_BALE_ACCOUNT, contact.id)
    second = service.enqueue_pending()
    assert second.queued == 0
    assert second.skipped_duplicate == 1


def test_worker_runs_account_check_only(session, settings) -> None:
    contact = _add_contact(session, "4", user_id="44")
    adapter = FakeBaleAdapter(
        accounts={
            contact.normalized_phone: BaleAccountCheckResult(
                status=BaleAccountStatus.HAS_ACCOUNT,
                bale_user_id="44",
            )
        }
    )
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.CHECK_BALE_ACCOUNT, contact.id)
    worker = build_account_check_worker(session, adapter, settings, interval_seconds=0)
    assert asyncio.run(worker.process_one()) is True
    session.refresh(contact)
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT
    job = queue.jobs.list_by_type(JobType.CHECK_BALE_ACCOUNT)[0]
    assert job.status is JobStatus.COMPLETED


def test_worker_skips_direct_invite_without_user_id(session, settings) -> None:
    contact = _add_contact(session, "5")
    adapter = FakeBaleAdapter()
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact.id)
    worker = build_account_check_worker(session, adapter, settings, interval_seconds=0)
    assert asyncio.run(worker.process_one()) is True
    job = queue.jobs.list_by_type(JobType.DIRECT_INVITE)[0]
    assert job.status is JobStatus.COMPLETED
    assert adapter.direct_invite_calls == []
    session.refresh(contact)
    assert contact.direct_invite_status.value == "SKIPPED"


def test_retryable_error_keeps_job_retrying(session, settings) -> None:
    contact = _add_contact(session, "6", user_id="66")

    class FlakyAdapter(FakeBaleAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
            self.calls += 1
            if self.calls == 1:
                raise RetryableBaleError("temporary 429")
            return BaleAccountCheckResult(status=BaleAccountStatus.HAS_ACCOUNT, bale_user_id="66")

    adapter = FlakyAdapter()
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.CHECK_BALE_ACCOUNT, contact.id)
    worker = build_account_check_worker(session, adapter, settings, interval_seconds=0)
    asyncio.run(worker.process_one())
    job = queue.jobs.list_by_type(JobType.CHECK_BALE_ACCOUNT)[0]
    assert job.status is JobStatus.RETRYING
    asyncio.run(worker.process_one())
    session.refresh(contact)
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT


def test_sync_shared_contacts_matches_phone(session, settings) -> None:
    contact = _add_contact(session, "7")
    adapter = FakeBaleAdapter(
        shared_contacts=[
            SharedContactUpdate(phone=contact.normalized_phone, bale_user_id="77", update_id=10)
        ]
    )
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    result = asyncio.run(service.sync_shared_contacts())
    assert result.matched == 1
    session.refresh(contact)
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT
    assert contact.bale_user_id == "77"
