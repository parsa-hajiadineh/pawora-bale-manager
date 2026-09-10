from __future__ import annotations

from sqlalchemy.orm import Session

from bale_inviter.database.models import Contact, utcnow
from bale_inviter.database.repositories import ContactRepository
from bale_inviter.domain.enums import (
    BaleAccountStatus,
    DirectInviteStatus,
    InviteLinkStatus,
    JoinStatus,
)
from bale_inviter.domain.status import (
    BALE_ACCOUNT_TRANSITIONS,
    DIRECT_INVITE_TRANSITIONS,
    INVITE_LINK_TRANSITIONS,
    JOIN_STATUS_TRANSITIONS,
    transition,
)


class ContactService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.contacts = ContactRepository(session)

    def get(self, contact_id: int) -> Contact:
        contact = self.contacts.get_by_id(contact_id)
        if contact is None:
            raise KeyError(f"Contact {contact_id} not found")
        return contact

    def set_bale_account_status(self, contact: Contact, status: BaleAccountStatus) -> Contact:
        contact.bale_account_status = transition(
            contact.bale_account_status, status, BALE_ACCOUNT_TRANSITIONS, "bale_account_status"
        )
        self.contacts.touch(contact)
        return contact

    def set_direct_invite_status(self, contact: Contact, status: DirectInviteStatus) -> Contact:
        contact.direct_invite_status = transition(
            contact.direct_invite_status, status, DIRECT_INVITE_TRANSITIONS, "direct_invite_status"
        )
        self.contacts.touch(contact)
        return contact

    def set_invite_link_status(self, contact: Contact, status: InviteLinkStatus) -> Contact:
        contact.invite_link_status = transition(
            contact.invite_link_status, status, INVITE_LINK_TRANSITIONS, "invite_link_status"
        )
        self.contacts.touch(contact)
        return contact

    def set_join_status(self, contact: Contact, status: JoinStatus) -> Contact:
        contact.join_status = transition(
            contact.join_status, status, JOIN_STATUS_TRANSITIONS, "join_status"
        )
        self.contacts.touch(contact)
        return contact

    def record_attempt(self, contact: Contact, error_message: str | None = None) -> Contact:
        contact.attempt_count += 1
        contact.last_attempt_at = utcnow()
        contact.error_message = error_message
        self.contacts.touch(contact)
        return contact
