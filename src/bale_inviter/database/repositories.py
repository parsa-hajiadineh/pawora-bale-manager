from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from bale_inviter.database.models import Contact, ImportBatch, Job, utcnow
from bale_inviter.domain.enums import ACTIVE_JOB_STATUSES, BaleAccountStatus, JobStatus, JobType


class ContactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, contact_id: int) -> Contact | None:
        return self.session.get(Contact, contact_id)

    def get_by_normalized_phone(self, normalized_phone: str) -> Contact | None:
        stmt = select(Contact).where(Contact.normalized_phone == normalized_phone)
        return self.session.scalars(stmt).first()

    def get_by_fingerprint(self, fingerprint: str) -> Contact | None:
        stmt = select(Contact).where(Contact.import_fingerprint == fingerprint)
        return self.session.scalars(stmt).first()

    def add(self, contact: Contact) -> Contact:
        self.session.add(contact)
        self.session.flush()
        return contact

    def list_all(self) -> list[Contact]:
        return list(self.session.scalars(select(Contact).order_by(Contact.id)).all())

    def count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(Contact)) or 0)

    def count_valid(self) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(Contact).where(Contact.is_valid.is_(True))) or 0
        )

    def count_invalid(self) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(Contact).where(Contact.is_valid.is_(False))) or 0
        )

    def count_by_bale_status(self, status: BaleAccountStatus) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Contact).where(Contact.bale_account_status == status)
            )
            or 0
        )

    def touch(self, contact: Contact) -> None:
        contact.updated_at = utcnow()


class ImportBatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, batch: ImportBatch) -> ImportBatch:
        self.session.add(batch)
        self.session.flush()
        return batch

    def latest(self) -> ImportBatch | None:
        stmt = select(ImportBatch).order_by(ImportBatch.id.desc())
        return self.session.scalars(stmt).first()


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, job_id: int) -> Job | None:
        return self.session.get(Job, job_id)

    def find_active_by_key(self, unique_key: str) -> Job | None:
        stmt: Select[tuple[Job]] = select(Job).where(
            Job.unique_key == unique_key,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
        return self.session.scalars(stmt).first()

    def add(self, job: Job) -> Job:
        self.session.add(job)
        self.session.flush()
        return job

    def claim_due(self, now: datetime | None = None) -> Job | None:
        current = now or utcnow()
        stmt = (
            select(Job)
            .where(
                Job.status.in_((JobStatus.PENDING, JobStatus.DELAYED, JobStatus.RETRYING)),
                Job.scheduled_at <= current,
            )
            .order_by(Job.scheduled_at.asc(), Job.id.asc())
            .limit(1)
        )
        job = self.session.scalars(stmt).first()
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.started_at = current
        job.attempts += 1
        job.updated_at = current
        self.session.flush()
        return job

    def list_by_type(self, job_type: JobType) -> list[Job]:
        stmt = select(Job).where(Job.job_type == job_type).order_by(Job.id)
        return list(self.session.scalars(stmt).all())
