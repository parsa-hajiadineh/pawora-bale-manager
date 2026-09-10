from pathlib import Path

from bale_inviter.database.models import Contact
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus
from bale_inviter.services.export import EXPORT_COLUMNS, ExportService


def test_export_report_writes_csv(session, settings, tmp_path: Path) -> None:
    session.add(
        Contact(
            name="Export User",
            phone="09124440001",
            normalized_phone="+989124440001",
            is_valid=True,
            import_fingerprint="fp-export-1",
            bale_user_id="301",
            bale_account_status=BaleAccountStatus.HAS_ACCOUNT,
            direct_invite_status=DirectInviteStatus.SUCCESS,
            error_message="ok",
        )
    )
    session.flush()
    target = tmp_path / "contacts.csv"
    result = ExportService(session, settings).export_csv(target)
    assert result.rows == 1
    text = target.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0]
    for column in EXPORT_COLUMNS:
        assert column in header
    assert "Export User" in text
    assert "+989124440001" in text
    assert "HAS_ACCOUNT" in text
    assert "SUCCESS" in text
