import asyncio

import pytest

from bale_inviter.adapters.bale import DirectInviteResult
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import DirectInviteStatus, InviteLinkStatus, JobStatus, JobType, JoinStatus
from bale_inviter.queue.models import DuplicateJobError
from bale_inviter.queue.service import QueueService
from bale_inviter.queue.worker import build_worker
from bale_inviter.services.invite import InviteService


def _add_contact(session, suffix: str, user_id: str | None = "10") -> Contact:
    contact = Contact(
        name=f"Invite {suffix}",
        phone=f"0912111000{suffix}",
        normalized_phone=f"+98912111000{suffix}",
        is_valid=True,
        import_fingerprint=f"fp-invite-{suffix}",
        bale_user_id=user_id,
    )
    session.add(contact)
    session.flush()
    return contact


def test_direct_invite_success(session, settings) -> None:
    contact = _add_contact(session, "1", "101")
    adapter = FakeBaleAdapter()
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_direct_invite(contact.id))
    assert result.status is DirectInviteStatus.SUCCESS
    assert contact.direct_invite_status is DirectInviteStatus.SUCCESS
    assert adapter.direct_invite_calls == [(contact.normalized_phone, settings.group_id, "101")]


def test_direct_invite_without_user_id_is_skipped(session, settings) -> None:
    contact = _add_contact(session, "2", None)
    adapter = FakeBaleAdapter()
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_direct_invite(contact.id))
    assert result.status is DirectInviteStatus.SKIPPED
    assert adapter.direct_invite_calls == []


def test_failed_direct_invite_enqueues_link_fallback(session, settings) -> None:
    contact = _add_contact(session, "3", "103")
    adapter = FakeBaleAdapter()
    adapter.invite_results["103"] = DirectInviteResult(status=DirectInviteStatus.FAILED, detail="forbidden")
    queue = QueueService(session, settings)
    service = InviteService(session, adapter, queue, settings)
    asyncio.run(service.process_direct_invite(contact.id))
    jobs = queue.jobs.list_by_type(JobType.SEND_INVITE_LINK)
    assert len(jobs) == 1
    assert contact.direct_invite_status is DirectInviteStatus.FAILED


def test_send_invite_link_success(session, settings) -> None:
    contact = _add_contact(session, "4", "104")
    adapter = FakeBaleAdapter()
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_invite_link(contact.id))
    assert result.status is InviteLinkStatus.SENT
    assert contact.invite_link_status is InviteLinkStatus.SENT
    assert adapter.send_link_calls[0][2] == "104"


def test_enqueue_invites_rejects_duplicates(session, settings) -> None:
    contact = _add_contact(session, "5", "105")
    adapter = FakeBaleAdapter()
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    first = service.enqueue_pending("direct")
    assert first.queued_direct == 1
    second = service.enqueue_pending("direct")
    assert second.queued_direct == 0
    assert second.skipped_duplicate == 1
    with pytest.raises(DuplicateJobError):
        QueueService(session, settings).enqueue_for_contact(JobType.DIRECT_INVITE, contact.id)


def test_worker_runs_direct_invite_and_join_check(session, settings) -> None:
    contact = _add_contact(session, "6", "106")
    adapter = FakeBaleAdapter()
    queue = QueueService(session, settings)
    queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact.id)
    worker = build_worker(session, adapter, settings, interval_seconds=0)
    assert asyncio.run(worker.process_one()) is True
    session.refresh(contact)
    assert contact.direct_invite_status is DirectInviteStatus.SUCCESS
    assert asyncio.run(worker.process_one()) is True
    session.refresh(contact)
    assert contact.join_status is JoinStatus.JOINED
    assert queue.jobs.list_by_type(JobType.DIRECT_INVITE)[0].status is JobStatus.COMPLETED


def test_enqueue_join_checks_for_invited_contacts(session, settings) -> None:
    invited = _add_contact(session, "7", "107")
    invited.direct_invite_status = DirectInviteStatus.SUCCESS
    linked = _add_contact(session, "8", "108")
    linked.invite_link_status = InviteLinkStatus.SENT
    joined = _add_contact(session, "9", "109")
    joined.direct_invite_status = DirectInviteStatus.SUCCESS
    joined.join_status = JoinStatus.JOINED
    pending = _add_contact(session, "0", "100")
    session.flush()
    adapter = FakeBaleAdapter()
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = service.enqueue_join_checks()
    assert result.eligible_join == 2
    assert result.queued_join == 2
    jobs = QueueService(session, settings).jobs.list_by_type(JobType.CHECK_JOIN_STATUS)
    ids = {job.contact_id for job in jobs}
    assert ids == {invited.id, linked.id}
    assert pending.id not in ids
    assert joined.id not in ids
