"""Preview what run-invites would queue, without Telegram login."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from bale_inviter.database.repositories import ContactRepository
from bale_inviter.domain.enums import BaleAccountStatus
from bale_inviter.reporting.service import ReportingService


@dataclass(slots=True)
class InvitePlan:
    summary: dict[str, int]
    would_check_accounts: int
    would_direct_invite: int
    would_send_link: int
    would_check_joins: int

    def as_dict(self) -> dict[str, int]:
        return {
            **self.summary,
            "would_check_accounts": self.would_check_accounts,
            "would_direct_invite": self.would_direct_invite,
            "would_send_link": self.would_send_link,
            "would_check_joins": self.would_check_joins,
        }


class PlanService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.contacts = ContactRepository(session)
        self.reporting = ReportingService(session)

    def build(self) -> InvitePlan:
        return InvitePlan(
            summary=self.reporting.as_dict(),
            would_check_accounts=len(
                self.contacts.list_valid_for_account_check((BaleAccountStatus.UNKNOWN,))
            ),
            would_direct_invite=len(self.contacts.list_for_direct_invite()),
            would_send_link=len(self.contacts.list_for_invite_link()),
            would_check_joins=len(self.contacts.list_for_join_check()),
        )
