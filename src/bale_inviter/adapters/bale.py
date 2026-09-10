"""Bale messenger adapter — interface only in phase 1.

No private messages, group invites, or bulk Bale operations are performed here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone


@dataclass(slots=True, frozen=True)
class BaleAccountCheckResult:
    status: BaleAccountStatus
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


class BaleAdapter(ABC):
    """Port for later Bale API / client integration."""

    @abstractmethod
    async def check_account(self, phone: str) -> BaleAccountCheckResult:
        """Return whether the phone has a Bale account. Must not send messages."""

    @abstractmethod
    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        """Invite the user into a group. Not implemented in phase 1."""

    @abstractmethod
    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        """Send an invite link as a private message. Not implemented in phase 1."""

    @abstractmethod
    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        """Check whether the user has joined the target group."""


class UnimplementedBaleAdapter(BaleAdapter):
    """Safe stub so the rest of the app can depend on a Bale port without calling Bale."""

    async def check_account(self, phone: str) -> BaleAccountCheckResult:
        raise NotImplementedError(
            f"check_account is not implemented in phase 1 (phone={mask_phone(phone)})"
        )

    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        raise NotImplementedError(
            f"direct_invite is not implemented in phase 1 (phone={mask_phone(phone)})"
        )

    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        raise NotImplementedError(
            f"send_invite_link is not implemented in phase 1 (phone={mask_phone(phone)})"
        )

    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        raise NotImplementedError(
            f"check_join_status is not implemented in phase 1 (phone={mask_phone(phone)})"
        )
