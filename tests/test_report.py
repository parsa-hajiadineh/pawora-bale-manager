from pathlib import Path

from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import BaleAccountStatus
from bale_inviter.importers.service import ImportService
from bale_inviter.reporting.service import ReportingService


def test_report_counts(session) -> None:
    session.add_all(
        [
            Contact(
                name="A",
                phone="09120000001",
                normalized_phone="+989120000001",
                is_valid=True,
                import_fingerprint="a",
                bale_account_status=BaleAccountStatus.UNKNOWN,
            ),
            Contact(
                name="B",
                phone="09120000002",
                normalized_phone="+989120000002",
                is_valid=True,
                import_fingerprint="b",
                bale_account_status=BaleAccountStatus.HAS_ACCOUNT,
            ),
            Contact(
                name="C",
                phone="09120000003",
                normalized_phone="+989120000003",
                is_valid=True,
                import_fingerprint="c",
                bale_account_status=BaleAccountStatus.NO_ACCOUNT,
            ),
            Contact(
                name="D",
                phone="bad",
                normalized_phone=None,
                is_valid=False,
                import_fingerprint="d",
            ),
        ]
    )
    session.flush()
    summary = ReportingService(session).as_dict()
    assert summary["total"] == 4
    assert summary["valid"] == 3
    assert summary["invalid"] == 1
    assert summary["unknown_bale_account"] == 2
    assert summary["has_bale_account"] == 1
    assert summary["no_bale_account"] == 1


def test_report_duplicate_from_last_import(session) -> None:
    source = Path(__file__).parent / "fixtures" / "sample_contacts.csv"
    ImportService(session).import_file(source)
    session.commit()
    summary = ReportingService(session).as_dict()
    assert summary["duplicate"] == 1
    assert summary["total"] >= 1
