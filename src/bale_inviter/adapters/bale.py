"""Bale messenger adapter port.

Phase 2 implements account lookup only. Direct invite, private invite-link
messages, and bulk Bale writes stay unimplemented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone


class RetryableBaleError(RuntimeError):
    """Transient Bale/API failure; the job queue should retry."""


class BaleConfigError(RuntimeError):
    """Missing or invalid Bale settings; do not retry as a job failure loop."""


@dataclass(slots=True, frozen=True)
class BaleBotInfo:
    id: int
    username: str | None
    first_name: str | None
    is_bot: bool


@dataclass(slots=True, frozen=True)
class BaleAccountCheckResult:
    status: BaleAccountStatus
    bale_user_id: str | None = None
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class DirectInviteResult:
    status: DirectInviteStatus
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class InviteLinkResult:
    status: InviteLinkStatus
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class JoinStatusResult:
    status: JoinStatus
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class SharedContactUpdate:
    phone: str
    bale_user_id: str
    update_id: int


class BaleAdapter(ABC):
    """Port for official Bale Bot API integration."""

    @abstractmethod
    async def verify_credentials(self) -> BaleBotInfo:
        """Call getMe. Must not send messages."""

    @abstractmethod
    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        """Return whether the phone/user has a Bale account. Must not send messages."""

    @abstractmethod
    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        """Read inbound getUpdates and return shared-contact payloads. Must not send messages."""

    @abstractmethod
    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        """Invite the user into a group. Not implemented in phase 2."""

    @abstractmethod
    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        """Send an invite link as a private message. Not implemented in phase 2."""

    @abstractmethod
    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        """Check whether the user has joined the target group. Not implemented in phase 2."""


class UnimplementedBaleAdapter(BaleAdapter):
    """Safe stub used when no Bale token is configured."""

    async def verify_credentials(self) -> BaleBotInfo:
        raise NotImplementedError("verify_credentials requires BALE_BOT_TOKEN")

    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        raise NotImplementedError(
            f"check_account is not configured (phone={mask_phone(phone)})"
        )

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        raise NotImplementedError("fetch_shared_contacts requires BALE_BOT_TOKEN")

    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        raise NotImplementedError(
            f"direct_invite is not implemented in phase 2 (phone={mask_phone(phone)})"
        )

    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        raise NotImplementedError(
            f"send_invite_link is not implemented in phase 2 (phone={mask_phone(phone)})"
        )

    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        raise NotImplementedError(
            f"check_join_status is not implemented in phase 2 (phone={mask_phone(phone)})"
        )
