import asyncio
import json

import httpx
import pytest

from bale_inviter.adapters.bale import BaleConfigError, RetryableBaleError
from bale_inviter.adapters.factory import create_bale_adapter
from bale_inviter.adapters.http import ALLOWED_METHODS, HttpBaleAdapter
from bale_inviter.config import Settings
from bale_inviter.domain.enums import BaleAccountStatus


def _client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, timeout=5.0)


def test_phase3_whitelist_includes_invite_and_dm() -> None:
    assert "sendMessage" in ALLOWED_METHODS
    assert "inviteUser" in ALLOWED_METHODS
    assert "deleteMessage" not in ALLOWED_METHODS


def test_http_check_without_user_id_does_not_call_api() -> None:
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        return httpx.Response(500, json={"ok": False, "description": "should not be called"})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.check_account("+989121234567"))
    assert result.status is BaleAccountStatus.UNKNOWN
    assert result.detail == "phone_lookup_unsupported"
    assert called == []


def test_http_getchat_has_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "sendMessage" not in str(request.url)
        assert request.url.path.endswith("/getChat")
        return httpx.Response(200, json={"ok": True, "result": {"id": 42, "type": "private", "first_name": "A"}})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.check_account("+989121234567", user_id="42"))
    assert result.status is BaleAccountStatus.HAS_ACCOUNT
    assert result.bale_user_id == "42"


def test_http_getchat_not_found_is_no_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.check_account("+989121234567", user_id="99"))
    assert result.status is BaleAccountStatus.NO_ACCOUNT


def test_http_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    with pytest.raises(RetryableBaleError):
        asyncio.run(adapter.check_account("+989121234567", user_id="1"))


def test_http_refuses_unallowed_method() -> None:
    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(lambda _r: httpx.Response(200, json={"ok": True})))
    with pytest.raises(RuntimeError, match="refuses method"):
        asyncio.run(adapter._call("deleteMessage", {"chat_id": 1, "message_id": 1}))


def test_http_redacts_token_from_errors() -> None:
    token = "SUPERSECRETTOKEN"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": f"bad {token}"})

    adapter = HttpBaleAdapter(token, client=_client(handler))
    result = asyncio.run(adapter.check_account("+989121234567", user_id="5"))
    assert result.status is BaleAccountStatus.ERROR
    assert token not in (result.detail or "")


def test_http_parses_shared_contact_updates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8") or "{}")
        assert body.get("timeout") == 0
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 8,
                        "message": {
                            "contact": {"phone_number": "09121234567", "user_id": 555},
                            "from": {"id": 555},
                        },
                    }
                ],
            },
        )

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    items, next_offset = asyncio.run(adapter.fetch_shared_contacts())
    assert len(items) == 1
    assert items[0].phone == "+989121234567"
    assert items[0].bale_user_id == "555"
    assert next_offset == 9


def test_http_verify_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getMe")
        return httpx.Response(
            200,
            json={"ok": True, "result": {"id": 7, "is_bot": True, "username": "tmp_bot", "first_name": "T"}},
        )

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    info = asyncio.run(adapter.verify_credentials())
    assert info.username == "tmp_bot"
    assert info.is_bot is True


def test_factory_requires_token_for_http() -> None:
    with pytest.raises(BaleConfigError):
        create_bale_adapter(
            Settings.model_construct(messenger_platform="http", bale_adapter="http", bale_bot_token="")
        )


def test_http_direct_invite_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/inviteUser")
        body = json.loads(request.content.decode("utf-8"))
        assert body["chat_id"] == -1001
        assert body["user_id"] == 42
        return httpx.Response(200, json={"ok": True, "result": True})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.direct_invite("+989121234567", "-1001", "42"))
    assert result.status.value == "SUCCESS"


def test_http_direct_invite_already_member_is_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "User already a member"})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.direct_invite("+989121234567", "-1001", "42"))
    assert result.status.value == "SUCCESS"


def test_http_send_invite_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sendMessage")
        body = json.loads(request.content.decode("utf-8"))
        assert "https://ble.ir/join/test" in body["text"]
        assert body["chat_id"] == 42
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(
        adapter.send_invite_link(
            "+989121234567",
            "https://ble.ir/join/test",
            "42",
            text="join https://ble.ir/join/test",
        )
    )
    assert result.status.value == "SENT"


def test_http_check_join_status_member() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getChatMember")
        return httpx.Response(200, json={"ok": True, "result": {"status": "member"}})

    adapter = HttpBaleAdapter("TESTTOKEN", client=_client(handler))
    result = asyncio.run(adapter.check_join_status("+989121234567", "-1001", "42"))
    assert result.status.value == "JOINED"
