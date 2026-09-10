"""Official Bale Bot HTTP adapter (tapi.bale.ai).

Phase 2 whitelist: getMe, getChat, getUpdates. No sendMessage, invite, or DMs.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    RetryableBaleError,
    SharedContactUpdate,
    UnimplementedBaleAdapter,
)
from bale_inviter.domain.enums import BaleAccountStatus
from bale_inviter.domain.phone import mask_phone, normalize_phone
from bale_inviter.logging_setup import log_event

PHASE2_ALLOWED_METHODS = frozenset({"getMe", "getChat", "getUpdates"})

_RETRYABLE_ERROR_SNIPPETS = (
    "too many requests",
    "retry after",
    "timeout",
    "timed out",
    "temporarily",
    "gateway",
    "bad gateway",
    "service unavailable",
)

_NOT_FOUND_SNIPPETS = (
    "chat not found",
    "user not found",
    "peer id invalid",
    "invalid user",
)


class HttpBaleAdapter(BaleAdapter):
    def __init__(
        self,
        token: str,
        base_url: str = "https://tapi.bale.ai",
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        cleaned = (token or "").strip()
        if not cleaned:
            raise ValueError("BALE_BOT_TOKEN is empty")
        self._token = cleaned
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def verify_credentials(self) -> BaleBotInfo:
        result = await self._call("getMe")
        return BaleBotInfo(
            id=int(result["id"]),
            username=result.get("username"),
            first_name=result.get("first_name"),
            is_bot=bool(result.get("is_bot", True)),
        )

    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        if user_id:
            return await self._check_by_chat_id(str(user_id))
        log_event(
            logging.WARNING,
            f"phone lookup is not supported by Bale Bot API phone={mask_phone(phone)}",
            operation="CHECK_BALE_ACCOUNT",
        )
        return BaleAccountCheckResult(
            status=BaleAccountStatus.UNKNOWN,
            detail="phone_lookup_unsupported",
        )

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        payload: dict[str, Any] = {"timeout": 0}
        if offset is not None:
            payload["offset"] = offset
        raw_updates = await self._call("getUpdates", payload)
        if not isinstance(raw_updates, list):
            return [], offset
        found: list[SharedContactUpdate] = []
        max_id = offset
        for item in raw_updates:
            if not isinstance(item, dict):
                continue
            update_id = int(item.get("update_id", 0))
            max_id = update_id if max_id is None else max(max_id, update_id)
            parsed = _parse_shared_contact(item)
            if parsed is not None:
                found.append(parsed)
        next_offset = None if max_id is None else max_id + 1
        return found, next_offset

    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        return await UnimplementedBaleAdapter().direct_invite(phone, group_id)

    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        return await UnimplementedBaleAdapter().send_invite_link(phone, invite_link)

    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        return await UnimplementedBaleAdapter().check_join_status(phone, group_id)

    async def _check_by_chat_id(self, chat_id: str) -> BaleAccountCheckResult:
        try:
            result = await self._call("getChat", {"chat_id": _as_chat_id(chat_id)})
        except RetryableBaleError:
            raise
        except BaleApiNotFoundError as exc:
            return BaleAccountCheckResult(
                status=BaleAccountStatus.NO_ACCOUNT,
                detail=str(exc),
            )
        except BaleApiError as exc:
            return BaleAccountCheckResult(
                status=BaleAccountStatus.ERROR,
                detail=str(exc),
            )
        user_id = str(result.get("id", chat_id))
        return BaleAccountCheckResult(
            status=BaleAccountStatus.HAS_ACCOUNT,
            bale_user_id=user_id,
            detail="getChat",
        )

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        if method not in PHASE2_ALLOWED_METHODS:
            raise RuntimeError(f"Phase 2 adapter refuses method={method}")
        url = f"{self._base_url}/bot{self._token}/{method}"
        try:
            result = await self._post(url, payload or {})
        except httpx.TimeoutException as exc:
            raise RetryableBaleError("Bale API timeout") from exc
        except httpx.HTTPError as exc:
            raise RetryableBaleError(self._redact(str(exc))) from exc
        return result

    async def _post(self, url: str, payload: dict[str, Any]) -> Any:
        client = self._client
        if client is None:
            async with httpx.AsyncClient(timeout=self._timeout) as owned:
                response = await owned.post(url, json=payload)
        else:
            response = await client.post(url, json=payload)

        body = _safe_json(response)
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            raise RetryableBaleError(
                f"Bale API HTTP {response.status_code}: {self._redact(_error_description(body))}"
            )
        if response.status_code >= 400:
            description = self._redact(_error_description(body) or f"HTTP {response.status_code}")
            if _is_not_found(description):
                raise BaleApiNotFoundError(description)
            raise BaleApiError(description)

        if not isinstance(body, dict):
            raise BaleApiError("Bale API returned a non-object body")
        if body.get("ok") is not True:
            description = self._redact(_error_description(body) or "unknown Bale error")
            if _is_retryable(response.status_code, description):
                raise RetryableBaleError(description)
            if _is_not_found(description):
                raise BaleApiNotFoundError(description)
            raise BaleApiError(description)
        return body.get("result")

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***")


class BaleApiError(RuntimeError):
    pass


class BaleApiNotFoundError(BaleApiError):
    pass


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"ok": False, "description": response.text[:200]}


def _error_description(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("description") or body.get("error") or "")
    return str(body)[:200]


def _is_not_found(description: str) -> bool:
    lowered = description.lower()
    return any(snippet in lowered for snippet in _NOT_FOUND_SNIPPETS)


def _is_retryable(status_code: int, description: str) -> bool:
    if status_code in {408, 429, 500, 502, 503, 504}:
        return True
    lowered = description.lower()
    return any(snippet in lowered for snippet in _RETRYABLE_ERROR_SNIPPETS)


def _as_chat_id(value: str) -> int | str:
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def _parse_shared_contact(update: dict[str, Any]) -> SharedContactUpdate | None:
    update_id = int(update.get("update_id") or 0)
    message = update.get("message") or update.get("edited_message") or {}
    if not isinstance(message, dict):
        return None
    contact = message.get("contact")
    if not isinstance(contact, dict):
        return None
    raw_phone = str(contact.get("phone_number") or "").strip()
    normalized = normalize_phone(raw_phone)
    if normalized is None:
        return None
    user_id = contact.get("user_id")
    if user_id is None:
        sender = message.get("from") or {}
        user_id = sender.get("id") if isinstance(sender, dict) else None
    if user_id is None:
        return None
    return SharedContactUpdate(
        phone=normalized,
        bale_user_id=str(user_id),
        update_id=update_id,
    )
