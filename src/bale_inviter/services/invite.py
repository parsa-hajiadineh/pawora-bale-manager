from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bale_inviter.adapters.bale import (
    BaleAdapter,
    BaleConfigError,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    RetryableBaleError,
)
from bale_inviter.config import Settings, get_settings
from bale_inviter.database.models import Contact
from bale_inviter.database.repositories import AppStateRepository, ContactRepository
from bale_inviter.domain.enums import DirectInviteStatus, InviteLinkStatus, JobType, JoinStatus
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.models import DuplicateJobError
from bale_inviter.queue.service import QueueService
from bale_inviter.services.contact_service import ContactService

INVITE_LINK_STATE_KEY = "group_invite_link"
CONTACT_SHARE_KEYBOARD = {
    "keyboard": [[{"text": "ارسال شماره موبایل", "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


@dataclass(slots=True)
class EnqueueInviteResult:
    queued_direct: int = 0
    queued_link: int = 0
    skipped_duplicate: int = 0
    skipped_no_user_id: int = 0
    eligible_direct: int = 0
    eligible_link: int = 0


class InviteService:
    """DIRECT_INVITE / SEND_INVITE_LINK / CHECK_JOIN_STATUS orchestration."""

    def __init__(
        self,
        session: Session,
        adapter: BaleAdapter,
        queue: QueueService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.adapter = adapter
        self.settings = settings or get_settings()
        self.contacts = ContactRepository(session)
        self.contact_service = ContactService(session)
        self.queue = queue or QueueService(session, self.settings)
        self.state = AppStateRepository(session)

    def enqueue_pending(self, strategy: str | None = None) -> EnqueueInviteResult:
        mode = (strategy or self.settings.invite_strategy or "auto").strip().lower()
        result = EnqueueInviteResult()
        if mode in {"direct", "auto"}:
            eligible = self.contacts.list_for_direct_invite()
            result.eligible_direct = len(eligible)
            for contact in eligible:
                try:
                    self.queue.enqueue_for_contact(JobType.DIRECT_INVITE, contact.id)
                    result.queued_direct += 1
                except DuplicateJobError:
                    result.skipped_duplicate += 1
        if mode == "link":
            eligible = self.contacts.list_for_invite_link()
            result.eligible_link = len(eligible)
            for contact in eligible:
                try:
                    self.queue.enqueue_for_contact(JobType.SEND_INVITE_LINK, contact.id)
                    result.queued_link += 1
                except DuplicateJobError:
                    result.skipped_duplicate += 1
        log_event(
            logging.INFO,
            (
                f"enqueued invites strategy={mode} direct={result.queued_direct} "
                f"link={result.queued_link} duplicate={result.skipped_duplicate}"
            ),
            operation="ENQUEUE_INVITES",
        )
        return result

    async def ensure_invite_link(self) -> str:
        configured = (self.settings.invite_link or "").strip()
        if configured:
            return configured
        cached = self.state.get(INVITE_LINK_STATE_KEY)
        if cached:
            return cached
        group_id = (self.settings.group_id or "").strip()
        if not group_id:
            raise BaleConfigError(
                "GROUP_ID and INVITE_LINK are empty. Add the bot to the group as admin, "
                "set GROUP_ID, then run prepare-group."
            )
        link = await self.adapter.export_invite_link(group_id)
        self.state.set(INVITE_LINK_STATE_KEY, link)
        log_event(logging.INFO, "exported group invite link", operation="EXPORT_INVITE_LINK")
        return link

    def format_invite_text(self, template: str | None = None) -> str:
        link = (self.settings.invite_link or "").strip() or self.state.get(INVITE_LINK_STATE_KEY) or ""
        raw = template or self.settings.invite_message
        return raw.replace("{invite_link}", link)

    async def process_direct_invite(self, contact_id: int) -> DirectInviteResult:
        contact = self.contact_service.get(contact_id)
        phone = contact.normalized_phone or contact.phone
        group_id = (self.settings.group_id or "").strip()
        log_event(
            logging.INFO,
            f"direct invite start phone={mask_phone(phone)}",
            operation="DIRECT_INVITE",
            contact_id=contact.id,
            attempt_count=contact.attempt_count + 1,
        )
        if not contact.bale_user_id:
            self.contact_service.record_attempt(contact, "missing_user_id")
            self.contact_service.set_direct_invite_status(contact, DirectInviteStatus.SKIPPED)
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_user_id")
        if not group_id:
            self.contact_service.record_attempt(contact, "missing_group_id")
            self.contact_service.set_direct_invite_status(contact, DirectInviteStatus.SKIPPED)
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_group_id")
        try:
            result = await self.adapter.direct_invite(phone, group_id, contact.bale_user_id)
        except RetryableBaleError as exc:
            self.contact_service.record_attempt(contact, str(exc))
            self.contact_service.set_direct_invite_status(contact, DirectInviteStatus.FAILED)
            log_event(
                logging.WARNING,
                f"direct invite retryable phone={mask_phone(phone)}",
                operation="DIRECT_INVITE",
                contact_id=contact.id,
                attempt_count=contact.attempt_count,
                error=str(exc),
            )
            raise
        self._apply_direct_result(contact, result)
        if result.status is DirectInviteStatus.FAILED and self._strategy() == "auto":
            self._enqueue_safe(JobType.SEND_INVITE_LINK, contact.id)
        if result.status is DirectInviteStatus.SUCCESS:
            self._enqueue_safe(JobType.CHECK_JOIN_STATUS, contact.id, delay_seconds=self.settings.invite_interval)
        return result

    async def process_invite_link(self, contact_id: int) -> InviteLinkResult:
        contact = self.contact_service.get(contact_id)
        phone = contact.normalized_phone or contact.phone
        log_event(
            logging.INFO,
            f"send invite link start phone={mask_phone(phone)}",
            operation="SEND_INVITE_LINK",
            contact_id=contact.id,
            attempt_count=contact.attempt_count + 1,
        )
        if not contact.bale_user_id:
            self.contact_service.record_attempt(contact, "missing_user_id")
            self.contact_service.set_invite_link_status(contact, InviteLinkStatus.FAILED)
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail="missing_user_id")
        link = await self.ensure_invite_link()
        text = self.format_invite_text()
        try:
            result = await self.adapter.send_invite_link(phone, link, contact.bale_user_id, text=text)
        except RetryableBaleError as exc:
            self.contact_service.record_attempt(contact, str(exc))
            self.contact_service.set_invite_link_status(contact, InviteLinkStatus.FAILED)
            raise
        error_message = None if result.status is InviteLinkStatus.SENT else result.detail
        self.contact_service.record_attempt(contact, error_message)
        self.contact_service.set_invite_link_status(contact, result.status)
        log_event(
            logging.INFO if result.status is InviteLinkStatus.SENT else logging.WARNING,
            f"invite link status={result.status.value} phone={mask_phone(phone)}",
            operation="SEND_INVITE_LINK",
            contact_id=contact.id,
            attempt_count=contact.attempt_count,
            error=result.detail if result.status is InviteLinkStatus.FAILED else None,
        )
        return result

    async def process_join_check(self, contact_id: int) -> JoinStatusResult:
        contact = self.contact_service.get(contact_id)
        phone = contact.normalized_phone or contact.phone
        group_id = (self.settings.group_id or "").strip()
        result = await self.adapter.check_join_status(phone, group_id, contact.bale_user_id)
        error_message = None if result.status is JoinStatus.JOINED else result.detail
        self.contact_service.record_attempt(contact, error_message)
        self.contact_service.set_join_status(contact, result.status)
        log_event(
            logging.INFO,
            f"join status={result.status.value} phone={mask_phone(phone)}",
            operation="CHECK_JOIN_STATUS",
            contact_id=contact.id,
            attempt_count=contact.attempt_count,
        )
        return result

    async def invite_user_now(self, user_id: str, phone: str | None = None) -> DirectInviteResult:
        group_id = (self.settings.group_id or "").strip()
        if not group_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_group_id")
        return await self.adapter.direct_invite(phone or "", group_id, user_id)

    def _apply_direct_result(self, contact: Contact, result: DirectInviteResult) -> None:
        phone = contact.normalized_phone or contact.phone
        error_message = None if result.status is DirectInviteStatus.SUCCESS else result.detail
        self.contact_service.record_attempt(contact, error_message)
        self.contact_service.set_direct_invite_status(contact, result.status)
        log_event(
            logging.INFO if result.status is DirectInviteStatus.SUCCESS else logging.WARNING,
            f"direct invite status={result.status.value} phone={mask_phone(phone)}",
            operation="DIRECT_INVITE",
            contact_id=contact.id,
            attempt_count=contact.attempt_count,
            error=result.detail if result.status is DirectInviteStatus.FAILED else None,
        )

    def _strategy(self) -> str:
        return (self.settings.invite_strategy or "auto").strip().lower()

    def _enqueue_safe(self, job_type: JobType, contact_id: int, delay_seconds: int = 0) -> None:
        try:
            self.queue.enqueue_for_contact(job_type, contact_id, delay_seconds=delay_seconds)
        except DuplicateJobError:
            log_event(
                logging.WARNING,
                "duplicate follow-up job skipped",
                operation=job_type.value,
                contact_id=contact_id,
            )
