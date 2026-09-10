from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from bale_inviter.database.repositories import ContactRepository, ImportBatchRepository
from bale_inviter.domain.enums import BaleAccountStatus


@dataclass(slots=True)
class ContactSummary:
    total: int
    valid: int
    invalid: int
    duplicate: int
    unknown_bale_account: int
    has_bale_account: int
    no_bale_account: int
    error_bale_account: int


class ReportingService:
    def __init__(self, session: Session) -> None:
        self.contacts = ContactRepository(session)
        self.batches = ImportBatchRepository(session)

    def summarize(self) -> ContactSummary:
        latest = self.batches.latest()
        duplicate = latest.duplicate_count if latest is not None else 0
        return ContactSummary(
            total=self.contacts.count(),
            valid=self.contacts.count_valid(),
            invalid=self.contacts.count_invalid(),
            duplicate=duplicate,
            unknown_bale_account=self.contacts.count_by_bale_status(BaleAccountStatus.UNKNOWN),
            has_bale_account=self.contacts.count_by_bale_status(BaleAccountStatus.HAS_ACCOUNT),
            no_bale_account=self.contacts.count_by_bale_status(BaleAccountStatus.NO_ACCOUNT),
            error_bale_account=self.contacts.count_by_bale_status(BaleAccountStatus.ERROR),
        )

    def as_dict(self) -> dict[str, int]:
        summary = self.summarize()
        return {
            "total": summary.total,
            "valid": summary.valid,
            "invalid": summary.invalid,
            "duplicate": summary.duplicate,
            "unknown_bale_account": summary.unknown_bale_account,
            "has_bale_account": summary.has_bale_account,
            "no_bale_account": summary.no_bale_account,
            "error_bale_account": summary.error_bale_account,
        }
