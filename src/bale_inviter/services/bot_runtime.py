from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from bale_inviter.adapters.bale import BaleAdapter, BotInboundMessage
from bale_inviter.config import Settings, get_settings
from bale_inviter.database.repositories import AppStateRepository, ContactRepository
from bale_inviter.domain.enums import BaleAccountStatus
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.service import QueueService
from bale_inviter.services.account_check import GET_UPDATES_OFFSET_KEY
from bale_inviter.services.contact_service import ContactService
from bale_inviter.services.invite import CONTACT_SHARE_KEYBOARD, InviteService


class BotRuntime:
    """Inbound update loop: /start replies, contact matching, and optional auto-invite."""

    def __init__(
        self,
        session: Session,
        adapter: BaleAdapter,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.adapter = adapter
        self.settings = settings or get_settings()
        self.contacts = ContactRepository(session)
        self.contact_service = ContactService(session)
        self.state = AppStateRepository(session)
        self.queue = QueueService(session, self.settings)
        self.invites = InviteService(session, adapter, self.queue, self.settings)

    async def process_inbound(self, *, timeout: int = 0) -> int:
        raw_offset = self.state.get(GET_UPDATES_OFFSET_KEY)
        offset = int(raw_offset) if raw_offset else None
        messages, next_offset = await self.adapter.fetch_inbound_messages(offset=offset, timeout=timeout)
        for item in messages:
            await self._handle(item)
        if next_offset is not None:
            self.state.set(GET_UPDATES_OFFSET_KEY, str(next_offset))
        if messages:
            log_event(
                logging.INFO,
                f"processed inbound updates count={len(messages)}",
                operation="BOT_RUNTIME",
            )
        return len(messages)

    async def _handle(self, item: BotInboundMessage) -> None:
        if item.chat_type in {"group", "supergroup"} and item.chat_id:
            log_event(
                logging.INFO,
                f"discovered group chat_id={item.chat_id} title={item.chat_title or '-'}",
                operation="BOT_RUNTIME",
            )
            return
        if item.phone:
            await self._handle_shared_contact(item)
            return
        if item.is_start:
            await self._handle_start(item)

    async def _handle_start(self, item: BotInboundMessage) -> None:
        chat_id = item.chat_id or item.user_id
        if not chat_id:
            return
        try:
            link = await self.invites.ensure_invite_link()
        except Exception as exc:  # noqa: BLE001 - still greet the user
            log_event(
                logging.WARNING,
                "could not resolve invite link for /start",
                operation="BOT_RUNTIME",
                error=str(exc),
            )
            link = (self.settings.invite_link or "").strip()
        text = self.settings.bot_start_message.replace("{invite_link}", link)
        await self.adapter.send_text(chat_id, text, CONTACT_SHARE_KEYBOARD)
        if item.user_id:
            contact = self.contacts.get_by_bale_user_id(item.user_id)
            if contact is not None:
                await self.invites.process_direct_invite(contact.id)
            elif self.settings.auto_invite_on_start:
                result = await self.invites.invite_user_now(item.user_id)
                log_event(
                    logging.INFO,
                    f"auto-invite on start status={result.status.value}",
                    operation="BOT_RUNTIME",
                    error=result.detail,
                )

    async def _handle_shared_contact(self, item: BotInboundMessage) -> None:
        if not item.phone:
            return
        contact = self.contacts.get_by_normalized_phone(item.phone)
        if contact is None:
            log_event(
                logging.WARNING,
                f"shared contact not in database phone={mask_phone(item.phone)}",
                operation="BOT_RUNTIME",
            )
            if item.user_id and self.settings.auto_invite_on_start:
                await self.invites.invite_user_now(item.user_id, item.phone)
            return
        if item.user_id:
            self.contact_service.set_bale_user_id(contact, item.user_id)
        self.contact_service.set_bale_account_status(contact, BaleAccountStatus.HAS_ACCOUNT)
        self.contact_service.record_attempt(contact, "shared_contact")
        log_event(
            logging.INFO,
            f"matched shared contact phone={mask_phone(item.phone)}",
            operation="BOT_RUNTIME",
            contact_id=contact.id,
            attempt_count=contact.attempt_count,
        )
        await self.invites.process_direct_invite(contact.id)
        if contact.direct_invite_status.value != "SUCCESS":
            await self.invites.process_invite_link(contact.id)
