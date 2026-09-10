from __future__ import annotations

from bale_inviter.adapters.bale import BaleAdapter, BaleConfigError, UnimplementedBaleAdapter
from bale_inviter.adapters.dry_run import DryRunAdapter
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.adapters.http import HttpBaleAdapter
from bale_inviter.adapters.telegram import TelegramUserAdapter, TelethonGateway
from bale_inviter.config import Settings, get_settings


def maybe_dry_run(
    adapter: BaleAdapter,
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
    allow_checks: bool = True,
) -> BaleAdapter:
    cfg = settings or get_settings()
    if dry_run or cfg.dry_run:
        return DryRunAdapter(adapter, allow_checks=allow_checks)
    return adapter


def create_bale_adapter(settings: Settings | None = None) -> BaleAdapter:
    cfg = settings or get_settings()
    name = _platform_name(cfg)
    if name == "fake":
        return FakeBaleAdapter()
    if name in {"none", "unimplemented", "stub"}:
        return UnimplementedBaleAdapter()
    if name in {"telegram", "telethon"}:
        return _create_telegram(cfg)
    if name in {"http", "bale"}:
        token = (cfg.bale_bot_token or "").strip()
        if not token:
            raise BaleConfigError(
                "BALE_BOT_TOKEN is empty. Put the BotFather token in .env; never commit it."
            )
        return HttpBaleAdapter(token=token, base_url=cfg.bale_api_base_url)
    raise BaleConfigError(
        f"Unknown MESSENGER_PLATFORM={name}. Use telegram, http, fake, or none."
    )


def _platform_name(cfg: Settings) -> str:
    platform = str(getattr(cfg, "messenger_platform", "") or "").strip().lower()
    adapter = str(getattr(cfg, "bale_adapter", "") or "").strip().lower()
    return platform or adapter or "telegram"


def _create_telegram(cfg: Settings) -> TelegramUserAdapter:
    api_id = int(getattr(cfg, "telegram_api_id", 0) or 0)
    api_hash = str(getattr(cfg, "telegram_api_hash", "") or "").strip()
    if not api_id or not api_hash:
        raise BaleConfigError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are empty. "
            "Create a free app at https://my.telegram.org and put the values in .env."
        )
    session_path = str(getattr(cfg, "telegram_session_path", "") or "./data/telegram.session")
    return TelegramUserAdapter(TelethonGateway(api_id, api_hash, session_path))
