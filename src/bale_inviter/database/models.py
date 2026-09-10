from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, Boolean, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bale_inviter.domain.enums import (
    BaleAccountStatus,
    DirectInviteStatus,
    InviteLinkStatus,
    JobStatus,
    JobType,
    JoinStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index(
            "uq_contacts_normalized_phone_valid",
            "normalized_phone",
            unique=True,
            sqlite_where=text("is_valid = 1 AND normalized_phone IS NOT NULL"),
        ),
        UniqueConstraint("import_fingerprint", name="uq_contacts_import_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    import_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bale_account_status: Mapped[BaleAccountStatus] = mapped_column(
        Enum(BaleAccountStatus, native_enum=False, length=32),
        nullable=False,
        default=BaleAccountStatus.UNKNOWN,
        index=True,
    )
    direct_invite_status: Mapped[DirectInviteStatus] = mapped_column(
        Enum(DirectInviteStatus, native_enum=False, length=32),
        nullable=False,
        default=DirectInviteStatus.NOT_STARTED,
    )
    invite_link_status: Mapped[InviteLinkStatus] = mapped_column(
        Enum(InviteLinkStatus, native_enum=False, length=32),
        nullable=False,
        default=InviteLinkStatus.NOT_SENT,
    )
    join_status: Mapped[JoinStatus] = mapped_column(
        Enum(JoinStatus, native_enum=False, length=32),
        nullable=False,
        default=JoinStatus.UNKNOWN,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="contact")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=64), nullable=False, index=True
    )
    unique_key: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

    contact: Mapped[Contact | None] = relationship(back_populates="jobs")
