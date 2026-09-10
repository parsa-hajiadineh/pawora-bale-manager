from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bale_inviter.domain.phone import mask_phone

_PHONE_PATTERN = re.compile(
    r"(?:\+98|0098|98|0)?9\d{9}"
)


class PhoneRedactingFilter(logging.Filter):
    """Strip raw mobile numbers from log messages and extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _PHONE_PATTERN.sub(_mask_match, record.msg)
        if record.args:
            record.args = tuple(
                _PHONE_PATTERN.sub(_mask_match, arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        for key in ("phone", "normalized_phone"):
            value = getattr(record, key, None)
            if isinstance(value, str):
                setattr(record, key, mask_phone(value))
        return True


def _mask_match(match: re.Match[str]) -> str:
    return mask_phone(match.group(0))


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.operation = getattr(record, "operation", "-")
        record.contact_id = getattr(record, "contact_id", "-")
        record.attempt_count = getattr(record, "attempt_count", "-")
        return super().format(record)


def setup_logging(log_level: str = "INFO", log_dir: str = "./logs") -> logging.Logger:
    logger = logging.getLogger("bale_inviter")
    if logger.handlers:
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        return logger

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    fmt = ContextFormatter(
        "%(asctime)s %(levelname)s operation=%(operation)s contact_id=%(contact_id)s "
        "attempts=%(attempt_count)s %(message)s"
    )
    redactor = PhoneRedactingFilter()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(redactor)
    logger.addHandler(console)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / "bale_inviter.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("bale_inviter")


def log_event(
    level: int,
    message: str,
    *,
    operation: str,
    contact_id: int | str | None = None,
    attempt_count: int | None = None,
    error: str | None = None,
    **extra: object,
) -> None:
    logger = get_logger()
    payload = {
        "operation": operation,
        "contact_id": "-" if contact_id is None else contact_id,
        "attempt_count": "-" if attempt_count is None else attempt_count,
        **extra,
    }
    if error:
        message = f"{message} error={error}"
    logger.log(level, message, extra=payload)
