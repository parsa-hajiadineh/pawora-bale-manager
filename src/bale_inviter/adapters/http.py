"""Official Bale Bot HTTP adapter (tapi.bale.ai).

Phase 3 whitelist: lookup, invite, invite-link DM, join check, and inbound updates.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    BotInboundMessage,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    RetryableBaleError,
    SharedContactUpdate,
)
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone, normalize_phone
from bale_inviter.logging_setup import log_event

ALLOWED_METHODS = frozenset(
    {
        "getMe",
        "getChat",
        "getChatMember",
        "getUpdates",
        "inviteUser",
        "sendMessage",
        "exportChatInviteLink",
        "createChatInviteLink",
    }
)
PHASE2_ALLOWED_METHODS = ALLOWED_METHODS
PHASE3_ALLOWED_METHODS = ALLOWED_METHODS

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

_ALREADY_MEMBER_SNIPPETS = (
    "already",
    "user_already_participant",
    "already a member",
    "already been added",
    "user already",
)

_JOINED_MEMBER_STATUSES = {"creator", "administrator", "member", "restricted"}


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
        inbound, next_offset = await self.fetch_inbound_messages(offset=offset, timeout=0)
        found = [
            SharedContactUpdate(phone=item.phone, bale_user_id=item.user_id, update_id=item.update_id)
            for item in inbound
            if item.phone and item.user_id
        ]
        return found, next_offset

    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        payload: dict[str, Any] = {"timeout": max(0, timeout)}
        if offset is not None:
            payload["offset"] = offset
        raw_updates = await self._call("getUpdates", payload)
        if not isinstance(raw_updates, list):
            return [], offset
        found: list[BotInboundMessage] = []
        max_id = offset
        for item in raw_updates:
            if not isinstance(item, dict):
                continue
            update_id = int(item.get("update_id", 0))
            max_id = update_id if max_id is None else max(max_id, update_id)
            found.append(_parse_inbound(item))
        next_offset = None if max_id is None else max_id + 1
        return found, next_offset

    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        if not user_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_user_id")
        if not group_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_group_id")
        try:
            await self._call(
                "inviteUser",
                {"chat_id": _as_chat_id(group_id), "user_id": _as_chat_id(user_id)},
            )
            return DirectInviteResult(status=DirectInviteStatus.SUCCESS, detail="inviteUser")
        except RetryableBaleError:
            raise
        except BaleApiError as exc:
            if _is_already_member(str(exc)):
                return DirectInviteResult(status=DirectInviteStatus.SUCCESS, detail="already_member")
            return DirectInviteResult(status=DirectInviteStatus.FAILED, detail=str(exc))

    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        if not user_id:
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail="missing_user_id")
        if not invite_link:
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail="missing_invite_link")
        message = text or invite_link
        try:
            await self._call(
                "sendMessage",
                {"chat_id": _as_chat_id(user_id), "text": message},
            )
            return InviteLinkResult(status=InviteLinkStatus.SENT, detail="sendMessage")
        except RetryableBaleError:
            raise
        except BaleApiError as exc:
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail=str(exc))

    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": _as_chat_id(chat_id), "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._call("sendMessage", payload)

    async def export_invite_link(self, group_id: str) -> str:
        try:
            result = await self._call("exportChatInviteLink", {"chat_id": _as_chat_id(group_id)})
            if isinstance(result, str) and result.strip():
                return result.strip()
        except BaleApiError:
            log_event(
                logging.WARNING,
                "exportChatInviteLink failed; trying createChatInviteLink",
                operation="EXPORT_INVITE_LINK",
            )
        result = await self._call("createChatInviteLink", {"chat_id": _as_chat_id(group_id)})
        if isinstance(result, dict) and result.get("invite_link"):
            return str(result["invite_link"]).strip()
        if isinstance(result, str) and result.strip():
            return result.strip()
        raise BaleApiError("Could not export invite link")

    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        if not user_id or not group_id:
            return JoinStatusResult(status=JoinStatus.UNKNOWN, detail="missing_user_or_group")
        try:
            result = await self._call(
                "getChatMember",
                {"chat_id": _as_chat_id(group_id), "user_id": _as_chat_id(user_id)},
            )
        except RetryableBaleError:
            raise
        except BaleApiNotFoundError as exc:
            return JoinStatusResult(status=JoinStatus.NOT_JOINED, detail=str(exc))
        except BaleApiError as exc:
            return JoinStatusResult(status=JoinStatus.UNKNOWN, detail=str(exc))
        member_status = ""
        if isinstance(result, dict):
            member_status = str(result.get("status") or "")
        if member_status.lower() in _JOINED_MEMBER_STATUSES:
            return JoinStatusResult(status=JoinStatus.JOINED, detail=member_status)
        return JoinStatusResult(status=JoinStatus.NOT_JOINED, detail=member_status or "unknown")

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
        if method not in ALLOWED_METHODS:
            raise RuntimeError(f"Phase 3 adapter refuses method={method}")
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


def _is_already_member(description: str) -> bool:
    lowered = description.lower()
    return any(snippet in lowered for snippet in _ALREADY_MEMBER_SNIPPETS)


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


def _parse_inbound(update: dict[str, Any]) -> BotInboundMessage:
    update_id = int(update.get("update_id") or 0)
    message = update.get("message") or update.get("edited_message") or {}
    if not isinstance(message, dict):
        return BotInboundMessage(update_id=update_id)
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    text = str(message.get("text") or "").strip()
    contact = message.get("contact") if isinstance(message.get("contact"), dict) else None
    phone = None
    user_id = sender.get("id")
    if contact:
        phone = normalize_phone(str(contact.get("phone_number") or ""))
        if contact.get("user_id") is not None:
            user_id = contact.get("user_id")
    return BotInboundMessage(
        update_id=update_id,
        user_id=str(user_id) if user_id is not None else None,
        chat_id=str(chat.get("id")) if chat.get("id") is not None else None,
        chat_type=str(chat.get("type")) if chat.get("type") else None,
        chat_title=str(chat.get("title")) if chat.get("title") else None,
        text=text or None,
        phone=phone,
        is_start=text.startswith("/start"),
    )
