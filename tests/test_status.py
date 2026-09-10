import pytest

from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import (
    BaleAccountStatus,
    DirectInviteStatus,
    InviteLinkStatus,
    JoinStatus,
)
from bale_inviter.domain.status import InvalidStatusTransition
from bale_inviter.services.contact_service import ContactService


def _contact(session) -> Contact:
    contact = Contact(
        name="Test",
        phone="09121234567",
        normalized_phone="+989121234567",
        is_valid=True,
        import_fingerprint="fp-test",
    )
    session.add(contact)
    session.flush()
    return contact


def test_bale_status_unknown_to_has_account(session) -> None:
    service = ContactService(session)
    contact = _contact(session)
    service.set_bale_account_status(contact, BaleAccountStatus.HAS_ACCOUNT)
    assert contact.bale_account_status is BaleAccountStatus.HAS_ACCOUNT


def test_direct_invite_success_is_terminal(session) -> None:
    service = ContactService(session)
    contact = _contact(session)
    service.set_direct_invite_status(contact, DirectInviteStatus.SUCCESS)
    with pytest.raises(InvalidStatusTransition):
        service.set_direct_invite_status(contact, DirectInviteStatus.FAILED)


def test_invite_link_failed_can_retry(session) -> None:
    service = ContactService(session)
    contact = _contact(session)
    service.set_invite_link_status(contact, InviteLinkStatus.FAILED)
    service.set_invite_link_status(contact, InviteLinkStatus.SENT)
    assert contact.invite_link_status is InviteLinkStatus.SENT


def test_join_status_joined_cannot_revert(session) -> None:
    service = ContactService(session)
    contact = _contact(session)
    service.set_join_status(contact, JoinStatus.JOINED)
    with pytest.raises(InvalidStatusTransition):
        service.set_join_status(contact, JoinStatus.NOT_JOINED)


def test_record_attempt_increments(session) -> None:
    service = ContactService(session)
    contact = _contact(session)
    service.record_attempt(contact, "timeout")
    assert contact.attempt_count == 1
    assert contact.error_message == "timeout"
    assert contact.last_attempt_at is not None
