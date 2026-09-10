import asyncio

import pytest

from bale_inviter.adapters.bale import BaleConfigError, RetryableBaleError
from bale_inviter.adapters.factory import create_bale_adapter
from bale_inviter.adapters.telegram import MemoryTelegramGateway, TelegramUserAdapter
from bale_inviter.config import Settings
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus


def test_telegram_lookup_by_phone_finds_account() -> None:
    gateway = MemoryTelegramGateway(phones={"+989121234567": "777"})
    adapter = TelegramUserAdapter(gateway)
    result = asyncio.run(adapter.check_account("+989121234567"))
    assert result.status is BaleAccountStatus.HAS_ACCOUNT
    assert result.bale_user_id == "777"
    assert gateway.lookup_calls == ["+989121234567"]


def test_telegram_lookup_by_phone_without_account() -> None:
    adapter = TelegramUserAdapter(MemoryTelegramGateway())
    result = asyncio.run(adapter.check_account("+989121234567"))
    assert result.status is BaleAccountStatus.NO_ACCOUNT


def test_telegram_direct_invite_by_phone() -> None:
    gateway = MemoryTelegramGateway(phones={"+989121234567": "777"})
    adapter = TelegramUserAdapter(gateway)
    result = asyncio.run(adapter.direct_invite("+989121234567", "-1001"))
    assert result.status is DirectInviteStatus.SUCCESS
    assert gateway.invite_calls == [("-1001", "777")]


def test_telegram_direct_invite_privacy_failure_is_failed() -> None:
    gateway = MemoryTelegramGateway()
    gateway.fail_invites["777"] = RuntimeError("UserPrivacyRestrictedError")
    adapter = TelegramUserAdapter(gateway)
    result = asyncio.run(adapter.direct_invite("+989121234567", "-1001", "777"))
    assert result.status is DirectInviteStatus.FAILED


def test_telegram_send_invite_link() -> None:
    adapter = TelegramUserAdapter(MemoryTelegramGateway())
    result = asyncio.run(
        adapter.send_invite_link("+989121234567", "https://t.me/+abc", "777", text="join https://t.me/+abc")
    )
    assert result.status is InviteLinkStatus.SENT


def test_telegram_join_status() -> None:
    gateway = MemoryTelegramGateway()
    gateway.members.add("777")
    adapter = TelegramUserAdapter(gateway)
    result = asyncio.run(adapter.check_join_status("+989121234567", "-1001", "777"))
    assert result.status is JoinStatus.JOINED


def test_telegram_retryable_invite() -> None:
    gateway = MemoryTelegramGateway()
    gateway.fail_invites["777"] = RetryableBaleError("Telegram flood wait 20s")
    adapter = TelegramUserAdapter(gateway)
    with pytest.raises(RetryableBaleError):
        asyncio.run(adapter.direct_invite("+989121234567", "-1001", "777"))


def test_factory_telegram_requires_api_keys() -> None:
    with pytest.raises(BaleConfigError):
        create_bale_adapter(
            Settings.model_construct(messenger_platform="telegram", telegram_api_id=0, telegram_api_hash="")
        )


def test_factory_http_still_requires_bot_token() -> None:
    with pytest.raises(BaleConfigError):
        create_bale_adapter(Settings.model_construct(messenger_platform="http", bale_bot_token=""))
