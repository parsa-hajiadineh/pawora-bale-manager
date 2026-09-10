from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from bale_inviter.database.repositories import ContactRepository, ImportBatchRepository, JobRepository
from bale_inviter.domain.enums import BaleAccountStatus, JobStatus, JobType


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
    with_bale_user_id: int
    pending_account_checks: int
    completed_account_checks: int
    failed_account_checks: int


class ReportingService:
    def __init__(self, session: Session) -> None:
        self.contacts = ContactRepository(session)
        self.batches = ImportBatchRepository(session)
        self.jobs = JobRepository(session)

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
            with_bale_user_id=self.contacts.count_with_bale_user_id(),
            pending_account_checks=self.jobs.count_by_type_status(
                JobType.CHECK_BALE_ACCOUNT, JobStatus.PENDING
            )
            + self.jobs.count_by_type_status(JobType.CHECK_BALE_ACCOUNT, JobStatus.DELAYED)
            + self.jobs.count_by_type_status(JobType.CHECK_BALE_ACCOUNT, JobStatus.RETRYING)
            + self.jobs.count_by_type_status(JobType.CHECK_BALE_ACCOUNT, JobStatus.RUNNING),
            completed_account_checks=self.jobs.count_by_type_status(
                JobType.CHECK_BALE_ACCOUNT, JobStatus.COMPLETED
            ),
            failed_account_checks=self.jobs.count_by_type_status(
                JobType.CHECK_BALE_ACCOUNT, JobStatus.FAILED
            ),
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
            "with_bale_user_id": summary.with_bale_user_id,
            "pending_account_checks": summary.pending_account_checks,
            "completed_account_checks": summary.completed_account_checks,
            "failed_account_checks": summary.failed_account_checks,
        }
