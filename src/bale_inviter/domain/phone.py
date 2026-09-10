from __future__ import annotations

import re

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NON_DIGIT = re.compile(r"\D+")


def to_english_digits(value: str) -> str:
    return value.translate(PERSIAN_DIGITS)


def mask_phone(phone: str | None) -> str:
    """Hide the middle of a phone number for logs and reports."""
    if not phone:
        return "***"
    compact = re.sub(r"\s+", "", phone.strip())
    if len(compact) <= 6:
        return "***"
    return f"{compact[:4]}***{compact[-2:]}"


def normalize_phone(raw: str | None) -> str | None:
    """Normalize Iranian mobile numbers to E.164 (`+989xxxxxxxxx`).

    Returns None when the value is missing or not a valid IR mobile number.
    """
    if raw is None:
        return None
    text = to_english_digits(str(raw)).strip()
    if not text:
        return None

    text = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    text = text.replace("\u200c", "").replace("\u00a0", "")

    if text.startswith("00"):
        text = "+" + text[2:]
    if text.startswith("98") and not text.startswith("+98"):
        text = "+" + text
    if text.startswith("+"):
        digits = _NON_DIGIT.sub("", text)
    else:
        digits = _NON_DIGIT.sub("", text)

    if digits.startswith("98"):
        national = digits[2:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        national = digits

    if len(national) != 10 or not national.startswith("9") or not national.isdigit():
        return None
    return f"+98{national}"


def is_valid_phone(raw: str | None) -> bool:
    return normalize_phone(raw) is not None
