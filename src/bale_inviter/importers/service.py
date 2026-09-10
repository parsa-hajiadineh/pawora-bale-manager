from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from bale_inviter.database.models import Contact, ImportBatch
from bale_inviter.database.repositories import ContactRepository, ImportBatchRepository
from bale_inviter.domain.phone import mask_phone, normalize_phone
from bale_inviter.importers.parser import parse_contacts_file
from bale_inviter.logging_setup import log_event


@dataclass(slots=True)
class ImportResult:
    source_filename: str
    total: int = 0
    valid: int = 0
    invalid: int = 0
    duplicate: int = 0
    created: int = 0
    updated: int = 0
    invalid_samples: list[str] = field(default_factory=list)


def fingerprint_for(name: str, phone: str, normalized_phone: str | None, is_valid: bool) -> str:
    if is_valid and normalized_phone:
        key = f"valid:{normalized_phone}"
    else:
        key = f"invalid:{phone.strip()}|{name.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ImportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.contacts = ContactRepository(session)
        self.batches = ImportBatchRepository(session)

    def import_file(self, path: str | Path) -> ImportResult:
        file_path = Path(path)
        rows = parse_contacts_file(file_path)
        result = ImportResult(source_filename=file_path.name, total=len(rows))
        seen_in_file: set[str] = set()

        log_event(
            logging.INFO,
            f"import started file={file_path.name} rows={len(rows)}",
            operation="IMPORT",
        )

        for row in rows:
            normalized = normalize_phone(row.phone)
            is_valid = normalized is not None
            fp = fingerprint_for(row.name, row.phone, normalized, is_valid)

            if fp in seen_in_file:
                result.duplicate += 1
                log_event(
                    logging.WARNING,
                    f"duplicate row skipped row={row.row_number} phone={mask_phone(row.phone)}",
                    operation="IMPORT",
                )
                continue
            seen_in_file.add(fp)

            if is_valid:
                result.valid += 1
            else:
                result.invalid += 1
                if len(result.invalid_samples) < 10:
                    result.invalid_samples.append(mask_phone(row.phone))

            existing = self.contacts.get_by_fingerprint(fp)
            if existing is None and normalized:
                existing = self.contacts.get_by_normalized_phone(normalized)

            if existing is not None:
                result.duplicate += 1
                result.updated += 1
                existing.name = row.name or existing.name
                existing.phone = row.phone or existing.phone
                existing.normalized_phone = normalized
                existing.is_valid = is_valid
                existing.extra_data = row.extra or existing.extra_data
                self.contacts.touch(existing)
                log_event(
                    logging.INFO,
                    f"contact updated phone={mask_phone(normalized or row.phone)}",
                    operation="IMPORT",
                    contact_id=existing.id,
                )
                continue

            contact = Contact(
                name=row.name or "بدون نام",
                phone=row.phone,
                normalized_phone=normalized,
                is_valid=is_valid,
                import_fingerprint=fp,
                extra_data=row.extra or None,
                error_message=None if is_valid else "invalid_phone",
            )
            self.contacts.add(contact)
            result.created += 1
            log_event(
                logging.INFO,
                f"contact created valid={is_valid} phone={mask_phone(normalized or row.phone)}",
                operation="IMPORT",
                contact_id=contact.id,
            )

        batch = ImportBatch(
            source_filename=file_path.name,
            total_rows=result.total,
            valid_count=result.valid,
            invalid_count=result.invalid,
            duplicate_count=result.duplicate,
            created_count=result.created,
            updated_count=result.updated,
        )
        self.batches.add(batch)
        self.session.flush()
        log_event(
            logging.INFO,
            (
                f"import finished file={file_path.name} total={result.total} valid={result.valid} "
                f"invalid={result.invalid} duplicate={result.duplicate} created={result.created} "
                f"updated={result.updated}"
            ),
            operation="IMPORT",
        )
        return result
