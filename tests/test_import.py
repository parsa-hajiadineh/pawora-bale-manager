from pathlib import Path

from openpyxl import Workbook

from bale_inviter.importers.parser import parse_contacts_file
from bale_inviter.importers.service import ImportService
from bale_inviter.database.repositories import ContactRepository


def test_parse_csv_fixture() -> None:
    path = Path(__file__).parent / "fixtures" / "sample_contacts.csv"
    rows = parse_contacts_file(path)
    assert len(rows) == 7
    assert rows[0].name == "علی رضایی"


def test_import_validates_and_deduplicates(session, tmp_path: Path) -> None:
    source = Path(__file__).parent / "fixtures" / "sample_contacts.csv"
    result = ImportService(session).import_file(source)
    session.commit()

    assert result.total == 7
    assert result.valid == 4
    assert result.invalid == 2
    assert result.duplicate == 1
    assert result.created == 6

    second = ImportService(session).import_file(source)
    session.commit()
    assert second.created == 0
    assert second.updated >= 1
    assert second.duplicate >= 1


def test_import_xlsx(session, tmp_path: Path) -> None:
    path = tmp_path / "contacts.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["نام", "شماره"])
    sheet.append(["سارا", "09123334444"])
    sheet.append(["سارا تکرار", "9123334444"])
    sheet.append(["نامعتبر", "abcd"])
    workbook.save(path)

    result = ImportService(session).import_file(path)
    session.commit()
    assert result.valid == 1
    assert result.invalid == 1
    assert result.duplicate == 1
    assert result.created == 2


def test_import_reads_optional_bale_user_id(session, tmp_path: Path) -> None:
    path = tmp_path / "with_ids.csv"
    path.write_text("name,phone,bale_user_id\nسارا,09123334444,12345\n", encoding="utf-8")
    result = ImportService(session).import_file(path)
    session.commit()
    assert result.created == 1
    contact = ContactRepository(session).get_by_normalized_phone("+989123334444")
    assert contact is not None
    assert contact.bale_user_id == "12345"
