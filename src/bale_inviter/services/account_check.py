from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bale_inviter.adapters.bale import BaleAdapter, BaleAccountCheckResult, RetryableBaleError
from bale_inviter.adapters.dry_run import is_dry_run_result
from bale_inviter.database.models import Contact
from bale_inviter.database.repositories import AppStateRepository, ContactRepository
from bale_inviter.domain.enums import BaleAccountStatus, JobType
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event
from bale_inviter.queue.models import DuplicateJobError
from bale_inviter.queue.service import QueueService
from bale_inviter.services.contact_service import ContactService

GET_UPDATES_OFFSET_KEY = "bale_get_updates_offset"


@dataclass(slots=True)
class EnqueueAccountChecksResult:
    queued: int = 0
    skipped_duplicate: int = 0
    skipped_no_user_id: int = 0
    eligible: int = 0


@dataclass(slots=True)
class SyncSharedContactsResult:
    scanned: int = 0
    matched: int = 0
    unmatched: int = 0


class AccountCheckService:
    """CHECK_BALE_ACCOUNT orchestration. Never invites or sends private messages."""

    def __init__(self, session: Session, adapter: BaleAdapter, queue: QueueService | None = None) -> None:
        self.session = session
        self.adapter = adapter
        self.contacts = ContactRepository(session)
        self.contact_service = ContactService(session)
        self.queue = queue or QueueService(session)
        self.state = AppStateRepository(session)

    def enqueue_pending(self, include_errors: bool = False) -> EnqueueAccountChecksResult:
        statuses = (BaleAccountStatus.UNKNOWN,)
        if include_errors:
            statuses = (BaleAccountStatus.UNKNOWN, BaleAccountStatus.ERROR)
        contacts = self.contacts.list_valid_for_account_check(statuses)
        result = EnqueueAccountChecksResult(eligible=len(contacts))
        for contact in contacts:
            if not contact.bale_user_id:
                result.skipped_no_user_id += 1
            try:
                self.queue.enqueue_for_contact(JobType.CHECK_BALE_ACCOUNT, contact.id)
                result.queued += 1
            except DuplicateJobError:
                result.skipped_duplicate += 1
        log_event(
            logging.INFO,
            (
                f"enqueued account checks queued={result.queued} "
                f"duplicate={result.skipped_duplicate} eligible={result.eligible}"
            ),
            operation="CHECK_BALE_ACCOUNT",
        )
        return result

    async def process_contact(self, contact_id: int) -> BaleAccountCheckResult:
        contact = self.contact_service.get(contact_id)
        phone = contact.normalized_phone or contact.phone
        log_event(
            logging.INFO,
            f"checking bale account phone={mask_phone(phone)} has_user_id={bool(contact.bale_user_id)}",
            operation="CHECK_BALE_ACCOUNT",
            contact_id=contact.id,
            attempt_count=contact.attempt_count + 1,
        )
        try:
            check = await self.adapter.check_account(phone, contact.bale_user_id)
        except RetryableBaleError as exc:
            self.contact_service.record_attempt(contact, str(exc))
            self.contact_service.set_bale_account_status(contact, BaleAccountStatus.ERROR)
            log_event(
                logging.WARNING,
                f"retryable bale error phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
                contact_id=contact.id,
                attempt_count=contact.attempt_count,
                error=str(exc),
            )
            raise
        except Exception as exc:  # noqa: BLE001 - persist then re-raise for the worker
            self.contact_service.record_attempt(contact, str(exc))
            self.contact_service.set_bale_account_status(contact, BaleAccountStatus.ERROR)
            log_event(
                logging.ERROR,
                f"account check failed phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
                contact_id=contact.id,
                attempt_count=contact.attempt_count,
                error=str(exc),
            )
            raise

        if is_dry_run_result(check.detail):
            log_event(
                logging.INFO,
                f"dry-run skipped persisting account check phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
                contact_id=contact.id,
            )
            return check
        self._apply_result(contact, check)
        return check

    def _apply_result(self, contact: Contact, check: BaleAccountCheckResult) -> None:
        phone = contact.normalized_phone or contact.phone
        error_message = None if check.status is BaleAccountStatus.HAS_ACCOUNT else check.detail
        self.contact_service.record_attempt(contact, error_message)
        if check.bale_user_id:
            self.contact_service.set_bale_user_id(contact, check.bale_user_id)
        if check.status is BaleAccountStatus.UNKNOWN and check.detail == "phone_lookup_unsupported":
            # Official Bot API cannot resolve a user from a phone number.
            log_event(
                logging.WARNING,
                f"left UNKNOWN; Bot API cannot resolve phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
                contact_id=contact.id,
                attempt_count=contact.attempt_count,
                error=check.detail,
            )
            return
        self.contact_service.set_bale_account_status(contact, check.status)
        level = logging.INFO if check.status is BaleAccountStatus.HAS_ACCOUNT else logging.WARNING
        log_event(
            level,
            f"account status={check.status.value} phone={mask_phone(phone)}",
            operation="CHECK_BALE_ACCOUNT",
            contact_id=contact.id,
            attempt_count=contact.attempt_count,
            error=check.detail if check.status is BaleAccountStatus.ERROR else None,
        )

    async def sync_shared_contacts(self) -> SyncSharedContactsResult:
        raw_offset = self.state.get(GET_UPDATES_OFFSET_KEY)
        offset = int(raw_offset) if raw_offset else None
        shared, next_offset = await self.adapter.fetch_shared_contacts(offset)
        result = SyncSharedContactsResult(scanned=len(shared))
        for item in shared:
            contact = self.contacts.get_by_normalized_phone(item.phone)
            if contact is None:
                result.unmatched += 1
                log_event(
                    logging.WARNING,
                    f"shared contact not in database phone={mask_phone(item.phone)}",
                    operation="SYNC_BOT_UPDATES",
                )
                continue
            self.contact_service.set_bale_user_id(contact, item.bale_user_id)
            self.contact_service.set_bale_account_status(contact, BaleAccountStatus.HAS_ACCOUNT)
            self.contact_service.record_attempt(contact, "shared_contact")
            result.matched += 1
            log_event(
                logging.INFO,
                f"matched shared contact phone={mask_phone(item.phone)}",
                operation="SYNC_BOT_UPDATES",
                contact_id=contact.id,
                attempt_count=contact.attempt_count,
            )
        if next_offset is not None:
            self.state.set(GET_UPDATES_OFFSET_KEY, str(next_offset))
        log_event(
            logging.INFO,
            f"sync updates scanned={result.scanned} matched={result.matched} unmatched={result.unmatched}",
            operation="SYNC_BOT_UPDATES",
        )
        return result
