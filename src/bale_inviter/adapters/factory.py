from __future__ import annotations

from bale_inviter.adapters.bale import BaleAdapter, BaleConfigError, UnimplementedBaleAdapter
from bale_inviter.adapters.fake import FakeBaleAdapter
from bale_inviter.adapters.http import HttpBaleAdapter
from bale_inviter.config import Settings, get_settings


def create_bale_adapter(settings: Settings | None = None) -> BaleAdapter:
    cfg = settings or get_settings()
    name = (cfg.bale_adapter or "http").strip().lower()
    if name == "fake":
        return FakeBaleAdapter()
    if name in {"none", "unimplemented", "stub"}:
        return UnimplementedBaleAdapter()
    if name != "http":
        raise BaleConfigError(f"Unknown BALE_ADAPTER={name}. Use http, fake, or none.")
    token = (cfg.bale_bot_token or "").strip()
    if not token:
        raise BaleConfigError(
            "BALE_BOT_TOKEN is empty. Put the BotFather token in .env; never commit it."
        )
    return HttpBaleAdapter(token=token, base_url=cfg.bale_api_base_url)
