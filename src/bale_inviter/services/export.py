"""Write a local CSV of contact statuses for Excel."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from bale_inviter.config import Settings, get_settings
from bale_inviter.database.models import Contact
from bale_inviter.database.repositories import ContactRepository
from bale_inviter.logging_setup import log_event

EXPORT_COLUMNS = (
    "id",
    "name",
    "phone",
    "normalized_phone",
    "is_valid",
    "bale_user_id",
    "bale_account_status",
    "direct_invite_status",
    "invite_link_status",
    "join_status",
    "attempt_count",
    "error_message",
)


@dataclass(slots=True, frozen=True)
class ExportResult:
    path: Path
    rows: int


class ExportService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.contacts = ContactRepository(session)

    def export_csv(self, path: Path | None = None) -> ExportResult:
        target = path or self._default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = self.contacts.list_all()
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for contact in rows:
                writer.writerow(self._row(contact))
        log_event(
            logging.INFO,
            f"exported {len(rows)} contacts to {target}",
            operation="EXPORT_REPORT",
        )
        return ExportResult(path=target, rows=len(rows))

    def _default_path(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return Path(self.settings.exports_dir) / f"contacts-{stamp}.csv"

    @staticmethod
    def _row(contact: Contact) -> dict[str, str | int]:
        return {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "normalized_phone": contact.normalized_phone or "",
            "is_valid": str(contact.is_valid).lower(),
            "bale_user_id": contact.bale_user_id or "",
            "bale_account_status": contact.bale_account_status.value,
            "direct_invite_status": contact.direct_invite_status.value,
            "invite_link_status": contact.invite_link_status.value,
            "join_status": contact.join_status.value,
            "attempt_count": contact.attempt_count,
            "error_message": contact.error_message or "",
        }
