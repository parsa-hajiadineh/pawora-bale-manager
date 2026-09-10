import asyncio

from bale_inviter.adapters.dry_run import DRY_RUN_DETAIL, DryRunAdapter
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import DirectInviteStatus, InviteLinkStatus, JobType, JoinStatus
from bale_inviter.queue.service import QueueService
from bale_inviter.services.account_check import AccountCheckService
from bale_inviter.services.invite import InviteService
from bale_inviter.services.plan import PlanService


def _add_contact(session, suffix: str, user_id: str | None = "10") -> Contact:
    contact = Contact(
        name=f"Dry {suffix}",
        phone=f"0912333000{suffix}",
        normalized_phone=f"+98912333000{suffix}",
        is_valid=True,
        import_fingerprint=f"fp-dry-{suffix}",
        bale_user_id=user_id,
    )
    session.add(contact)
    session.flush()
    return contact


def test_dry_run_does_not_call_inner_invite_or_persist(session, settings) -> None:
    contact = _add_contact(session, "1", "201")
    inner = FakeBaleAdapter()
    adapter = DryRunAdapter(inner)
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_direct_invite(contact.id))
    assert result.detail == DRY_RUN_DETAIL
    assert inner.direct_invite_calls == []
    assert contact.direct_invite_status is DirectInviteStatus.NOT_STARTED
    assert contact.attempt_count == 0
    assert adapter.invite_previews == [(contact.normalized_phone, "201")]


def test_dry_run_invite_link_does_not_persist(session, settings) -> None:
    contact = _add_contact(session, "2", "202")
    inner = FakeBaleAdapter()
    adapter = DryRunAdapter(inner)
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_invite_link(contact.id))
    assert result.detail == DRY_RUN_DETAIL
    assert inner.send_link_calls == []
    assert contact.invite_link_status is InviteLinkStatus.NOT_SENT


def test_dry_run_join_check_does_not_persist(session, settings) -> None:
    contact = _add_contact(session, "3", "203")
    inner = FakeBaleAdapter()
    adapter = DryRunAdapter(inner)
    service = InviteService(session, adapter, QueueService(session, settings), settings)
    result = asyncio.run(service.process_join_check(contact.id))
    assert result.detail == DRY_RUN_DETAIL
    assert inner.join_checks == []
    assert contact.join_status is JoinStatus.UNKNOWN


def test_dry_run_still_runs_account_checks_when_allowed(session, settings) -> None:
    contact = _add_contact(session, "4", "204")
    inner = FakeBaleAdapter()
    adapter = DryRunAdapter(inner, allow_checks=True)
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    result = asyncio.run(service.process_contact(contact.id))
    assert result.status.value == "HAS_ACCOUNT"
    assert inner.check_calls
    assert contact.bale_user_id == "204"


def test_dry_run_skips_account_checks_when_disallowed(session, settings) -> None:
    contact = _add_contact(session, "5", None)
    inner = FakeBaleAdapter()
    adapter = DryRunAdapter(inner, allow_checks=False)
    service = AccountCheckService(session, adapter, QueueService(session, settings))
    result = asyncio.run(service.process_contact(contact.id))
    assert result.detail == DRY_RUN_DETAIL
    assert inner.check_calls == []
    assert contact.bale_account_status.value == "UNKNOWN"
    assert contact.attempt_count == 0


def test_plan_counts_without_queueing(session) -> None:
    unknown = _add_contact(session, "6", None)
    ready = _add_contact(session, "7", "207")
    invited = _add_contact(session, "8", "208")
    invited.direct_invite_status = DirectInviteStatus.SUCCESS
    session.flush()
    preview = PlanService(session).build()
    assert preview.would_check_accounts >= 1
    assert preview.would_direct_invite >= 1
    assert preview.would_check_joins == 1
    assert unknown.id and ready.id
    assert QueueService(session).jobs.list_by_type(JobType.DIRECT_INVITE) == []
