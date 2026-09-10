"""Bale messenger adapter port.

Phase 3 supports account lookup, direct group invite, invite-link DMs,
join checks, and inbound bot updates. Operations go through the job queue
and official Bot API only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone


class RetryableBaleError(RuntimeError):
    """Transient Bale/API failure; the job queue should retry."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


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


@dataclass(slots=True, frozen=True)
class BotInboundMessage:
    update_id: int
    user_id: str | None = None
    chat_id: str | None = None
    chat_type: str | None = None
    chat_title: str | None = None
    text: str | None = None
    phone: str | None = None
    is_start: bool = False


class BaleAdapter(ABC):
    """Port for official Bale Bot API integration."""

    @abstractmethod
    async def verify_credentials(self) -> BaleBotInfo:
        """Call getMe."""

    @abstractmethod
    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        """Return whether the phone/user has a Bale account."""

    @abstractmethod
    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        """Read inbound getUpdates and return shared-contact payloads."""

    @abstractmethod
    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        """Read inbound getUpdates (starts, contacts, group chats)."""

    @abstractmethod
    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        """Invite the user into a group via inviteUser."""

    @abstractmethod
    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        """Send an invite link as a private message."""

    @abstractmethod
    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        """Send a text message. Used for /start replies."""

    @abstractmethod
    async def export_invite_link(self, group_id: str) -> str:
        """Create or export the group's invite link."""

    @abstractmethod
    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        """Check whether the user has joined the target group."""


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

    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        raise NotImplementedError("fetch_inbound_messages requires BALE_BOT_TOKEN")

    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        raise NotImplementedError(
            f"direct_invite is not configured (phone={mask_phone(phone)})"
        )

    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        raise NotImplementedError(
            f"send_invite_link is not configured (phone={mask_phone(phone)})"
        )

    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        raise NotImplementedError("send_text is not configured")

    async def export_invite_link(self, group_id: str) -> str:
        raise NotImplementedError("export_invite_link is not configured")

    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        raise NotImplementedError(
            f"check_join_status is not configured (phone={mask_phone(phone)})"
        )
