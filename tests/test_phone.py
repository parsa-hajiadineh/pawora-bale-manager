from bale_inviter.domain.phone import is_valid_phone, mask_phone, normalize_phone


def test_normalize_local_mobile() -> None:
    assert normalize_phone("09121234567") == "+989121234567"


def test_normalize_without_zero() -> None:
    assert normalize_phone("9121234567") == "+989121234567"


def test_normalize_plus_country_code() -> None:
    assert normalize_phone("+989121234567") == "+989121234567"


def test_normalize_00_prefix() -> None:
    assert normalize_phone("00989121234567") == "+989121234567"


def test_normalize_persian_digits() -> None:
    assert normalize_phone("۰۹۱۲۱۲۳۴۵۶۷") == "+989121234567"


def test_normalize_with_spaces_and_dashes() -> None:
    assert normalize_phone("0912 123-4567") == "+989121234567"


def test_invalid_too_short() -> None:
    assert normalize_phone("0912123") is None
    assert is_valid_phone("0912123") is False


def test_invalid_landline() -> None:
    assert normalize_phone("02112345678") is None


def test_empty_and_none() -> None:
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_mask_phone_hides_middle() -> None:
    masked = mask_phone("+989121234567")
    assert "123456" not in masked
    assert masked.startswith("+989")
    assert "***" in masked
