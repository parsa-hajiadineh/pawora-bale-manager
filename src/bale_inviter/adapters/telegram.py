"""Telegram user-account adapter (Telethon / official MTProto).

Unlike a Telegram bot, a logged-in user account can resolve phone numbers via
contacts.importContacts and invite those users into a group. This is the path
that works with a name+phone Excel list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    BaleConfigError,
    BotInboundMessage,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    RetryableBaleError,
    SharedContactUpdate,
)
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import mask_phone
from bale_inviter.logging_setup import log_event


class TelegramGateway(Protocol):
    async def get_me(self) -> BaleBotInfo: ...

    async def lookup_phone(self, phone: str) -> str | None: ...

    async def invite_to_group(self, group_id: str, user_id: str) -> None: ...

    async def send_message(self, user_id: str, text: str) -> None: ...

    async def export_link(self, group_id: str) -> str: ...

    async def is_member(self, group_id: str, user_id: str) -> bool | None: ...


@dataclass
class MemoryTelegramGateway:
    """In-memory Telegram gateway for tests. Does not use the network."""

    phones: dict[str, str] = field(default_factory=dict)
    members: set[str] = field(default_factory=set)
    invite_link: str = "https://t.me/+testinvite"
    me: BaleBotInfo = field(
        default_factory=lambda: BaleBotInfo(id=9, username="me", first_name="Me", is_bot=False)
    )
    lookup_calls: list[str] = field(default_factory=list)
    invite_calls: list[tuple[str, str]] = field(default_factory=list)
    send_calls: list[tuple[str, str]] = field(default_factory=list)
    fail_invites: dict[str, Exception] = field(default_factory=dict)

    async def get_me(self) -> BaleBotInfo:
        return self.me

    async def lookup_phone(self, phone: str) -> str | None:
        self.lookup_calls.append(phone)
        return self.phones.get(phone)

    async def invite_to_group(self, group_id: str, user_id: str) -> None:
        self.invite_calls.append((group_id, user_id))
        if user_id in self.fail_invites:
            raise self.fail_invites[user_id]
        self.members.add(user_id)

    async def send_message(self, user_id: str, text: str) -> None:
        self.send_calls.append((user_id, text))

    async def export_link(self, group_id: str) -> str:
        return self.invite_link

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        return user_id in self.members


class TelegramUserAdapter(BaleAdapter):
    """Messenger port backed by a Telegram user session."""

    def __init__(self, gateway: TelegramGateway) -> None:
        self.gateway = gateway

    async def verify_credentials(self) -> BaleBotInfo:
        return await self.gateway.get_me()

    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        if user_id:
            return BaleAccountCheckResult(
                status=BaleAccountStatus.HAS_ACCOUNT,
                bale_user_id=str(user_id),
                detail="known_user_id",
            )
        found = await self.gateway.lookup_phone(phone)
        if found:
            log_event(
                logging.INFO,
                f"telegram account found phone={mask_phone(phone)}",
                operation="CHECK_BALE_ACCOUNT",
            )
            return BaleAccountCheckResult(
                status=BaleAccountStatus.HAS_ACCOUNT,
                bale_user_id=str(found),
                detail="importContacts",
            )
        log_event(
            logging.INFO,
            f"telegram account missing phone={mask_phone(phone)}",
            operation="CHECK_BALE_ACCOUNT",
        )
        return BaleAccountCheckResult(status=BaleAccountStatus.NO_ACCOUNT, detail="not_on_telegram")

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        return [], offset

    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        return [], offset

    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        target_id = user_id
        if not target_id:
            target_id = await self.gateway.lookup_phone(phone)
        if not target_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_user_id")
        if not group_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_group_id")
        try:
            await self.gateway.invite_to_group(group_id, str(target_id))
            return DirectInviteResult(status=DirectInviteStatus.SUCCESS, detail="inviteToGroup")
        except RetryableBaleError:
            raise
        except Exception as exc:  # noqa: BLE001 - map Telegram privacy/admin errors
            detail = str(exc)
            lowered = detail.lower()
            if "already" in lowered or "user_already_participant" in lowered:
                return DirectInviteResult(status=DirectInviteStatus.SUCCESS, detail="already_member")
            return DirectInviteResult(status=DirectInviteStatus.FAILED, detail=detail)

    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        target_id = user_id
        if not target_id:
            target_id = await self.gateway.lookup_phone(phone)
        if not target_id:
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail="missing_user_id")
        message = text or invite_link
        try:
            await self.gateway.send_message(str(target_id), message)
            return InviteLinkResult(status=InviteLinkStatus.SENT, detail="sendMessage")
        except RetryableBaleError:
            raise
        except Exception as exc:  # noqa: BLE001
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail=str(exc))

    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        await self.gateway.send_message(str(chat_id), text)

    async def export_invite_link(self, group_id: str) -> str:
        return await self.gateway.export_link(group_id)

    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        target_id = user_id
        if not target_id:
            target_id = await self.gateway.lookup_phone(phone)
        if not target_id or not group_id:
            return JoinStatusResult(status=JoinStatus.UNKNOWN, detail="missing_user_or_group")
        member = await self.gateway.is_member(group_id, str(target_id))
        if member is True:
            return JoinStatusResult(status=JoinStatus.JOINED, detail="member")
        if member is False:
            return JoinStatusResult(status=JoinStatus.NOT_JOINED, detail="not_participant")
        return JoinStatusResult(status=JoinStatus.UNKNOWN, detail="unknown")


class TelethonGateway:
    """Real Telethon client. Session file must already be authorized."""

    def __init__(self, api_id: int, api_hash: str, session_path: str) -> None:
        if not api_id or not api_hash.strip():
            raise BaleConfigError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
        self.api_id = int(api_id)
        self.api_hash = api_hash.strip()
        self.session_path = session_path
        self._client = None

    async def _client_connected(self):
        from telethon import TelegramClient

        if self._client is None:
            path = Path(self.session_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._client = TelegramClient(str(path), self.api_id, self.api_hash)
        if not self._client.is_connected():
            await self._client.connect()
        if not await self._client.is_user_authorized():
            raise BaleConfigError(
                "Telegram session is not logged in. Run: python -m bale_inviter telegram-login"
            )
        return self._client

    async def get_me(self) -> BaleBotInfo:
        client = await self._client_connected()
        me = await client.get_me()
        return BaleBotInfo(
            id=int(me.id),
            username=getattr(me, "username", None),
            first_name=getattr(me, "first_name", None),
            is_bot=bool(getattr(me, "bot", False)),
        )

    async def lookup_phone(self, phone: str) -> str | None:
        from telethon.tl.functions.contacts import ImportContactsRequest
        from telethon.tl.types import InputPhoneContact

        client = await self._client_connected()
        try:
            result = await client(
                ImportContactsRequest(
                    [
                        InputPhoneContact(
                            client_id=0,
                            phone=phone,
                            first_name="Col",
                            last_name="",
                        )
                    ]
                )
            )
        except Exception as exc:
            _raise_telegram(exc)
        users = getattr(result, "users", None) or []
        if not users:
            return None
        return str(users[0].id)

    async def invite_to_group(self, group_id: str, user_id: str) -> None:
        from telethon.tl.functions.channels import InviteToChannelRequest
        from telethon.tl.functions.messages import AddChatUserRequest
        from telethon.tl.types import Channel, Chat

        client = await self._client_connected()
        try:
            chat = await client.get_entity(_parse_peer(group_id))
            user = await client.get_entity(int(user_id))
            if isinstance(chat, Channel):
                await client(InviteToChannelRequest(chat, [user]))
            elif isinstance(chat, Chat):
                await client(AddChatUserRequest(chat.id, user, fwd_limit=0))
            else:
                await client(InviteToChannelRequest(chat, [user]))
        except Exception as exc:
            _raise_telegram(exc)

    async def send_message(self, user_id: str, text: str) -> None:
        client = await self._client_connected()
        try:
            await client.send_message(_parse_peer(user_id), text)
        except Exception as exc:
            _raise_telegram(exc)

    async def export_link(self, group_id: str) -> str:
        from telethon.tl.functions.messages import ExportChatInviteRequest

        client = await self._client_connected()
        try:
            chat = await client.get_entity(_parse_peer(group_id))
            result = await client(ExportChatInviteRequest(peer=chat))
        except Exception as exc:
            _raise_telegram(exc)
        link = getattr(result, "link", None)
        if not link:
            raise RuntimeError("Telegram did not return an invite link")
        return str(link)

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        from telethon.errors import UserNotParticipantError

        client = await self._client_connected()
        try:
            chat = await client.get_entity(_parse_peer(group_id))
            user = await client.get_entity(int(user_id))
            await client.get_permissions(chat, user)
            return True
        except UserNotParticipantError:
            return False
        except Exception as exc:
            _raise_telegram(exc)
            return None


def _parse_peer(value: str) -> int | str:
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def _raise_telegram(exc: Exception) -> None:
    name = type(exc).__name__
    detail = str(exc)
    wait = getattr(exc, "seconds", None)
    if name == "FloodWaitError" or "wait of" in detail.lower() or wait:
        seconds = int(wait or 60)
        raise RetryableBaleError(f"Telegram flood wait {seconds}s") from exc
    if name in {"AuthKeyUnregisteredError", "SessionRevokedError"}:
        raise BaleConfigError("Telegram session expired. Run telegram-login again.") from exc
    raise RuntimeError(f"{name}: {detail}") from exc


async def login_telegram_session(
    api_id: int,
    api_hash: str,
    session_path: str,
    phone: str,
    code_callback,
    password_callback=None,
) -> BaleBotInfo:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    path = Path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(path), int(api_id), api_hash.strip())
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            return BaleBotInfo(
                id=int(me.id),
                username=getattr(me, "username", None),
                first_name=getattr(me, "first_name", None),
                is_bot=False,
            )
        await client.send_code_request(phone)
        code = code_callback()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            if password_callback is None:
                raise BaleConfigError("This account has 2FA; provide the cloud password.") from None
            await client.sign_in(password=password_callback())
        me = await client.get_me()
        return BaleBotInfo(
            id=int(me.id),
            username=getattr(me, "username", None),
            first_name=getattr(me, "first_name", None),
            is_bot=False,
        )
    finally:
        await client.disconnect()
