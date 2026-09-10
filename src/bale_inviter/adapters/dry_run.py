"""Wrap a real adapter so invites and DMs are not sent."""

from __future__ import annotations

import logging

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    BotInboundMessage,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    SharedContactUpdate,
)
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event

DRY_RUN_DETAIL = "dry_run"


def is_dry_run_result(detail: str | None) -> bool:
    return detail == DRY_RUN_DETAIL


class DryRunAdapter(BaleAdapter):
    """Pass through account lookup; skip invites, DMs, and join mutations."""

    def __init__(self, inner: BaleAdapter, *, allow_checks: bool = True) -> None:
        self.inner = inner
        self.allow_checks = allow_checks
        self.invite_previews: list[tuple[str, str | None]] = []
        self.link_previews: list[tuple[str, str | None]] = []
        self.join_previews: list[tuple[str, str | None]] = []

    async def verify_credentials(self) -> BaleBotInfo:
        return await self.inner.verify_credentials()

    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        if not self.allow_checks:
            log_event(
                logging.INFO,
                f"dry-run skipped account check phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
            )
            return BaleAccountCheckResult(status=BaleAccountStatus.UNKNOWN, detail=DRY_RUN_DETAIL)
        return await self.inner.check_account(phone, user_id)

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        return await self.inner.fetch_shared_contacts(offset)

    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        return await self.inner.fetch_inbound_messages(offset, timeout)

    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        self.invite_previews.append((phone, user_id))
        log_event(
            logging.INFO,
            f"dry-run would direct-invite phone={mask_phone(phone)}",
            operation="DIRECT_INVITE",
        )
        return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail=DRY_RUN_DETAIL)

    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        self.link_previews.append((phone, user_id))
        log_event(
            logging.INFO,
            f"dry-run would send invite link phone={mask_phone(phone)}",
            operation="SEND_INVITE_LINK",
        )
        return InviteLinkResult(status=InviteLinkStatus.NOT_SENT, detail=DRY_RUN_DETAIL)

    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        log_event(logging.INFO, "dry-run skipped send_text", operation="SEND_TEXT")

    async def export_invite_link(self, group_id: str) -> str:
        return await self.inner.export_invite_link(group_id)

    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        self.join_previews.append((phone, user_id))
        log_event(
            logging.INFO,
            f"dry-run skipped join check phone={mask_phone(phone)}",
            operation="CHECK_JOIN_STATUS",
        )
        return JoinStatusResult(status=JoinStatus.UNKNOWN, detail=DRY_RUN_DETAIL)
