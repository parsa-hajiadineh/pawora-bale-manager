"""In-memory Bale adapter for tests. Does not call the network."""

from __future__ import annotations

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    BotInboundMessage,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    SharedContactUpdate,
)
from bale_inviter.domain.enums import BaleAccountStatus, DirectInviteStatus, InviteLinkStatus, JoinStatus
from bale_inviter.domain.phone import normalize_phone


class FakeBaleAdapter(BaleAdapter):
    def __init__(
        self,
        accounts: dict[str, BaleAccountCheckResult] | None = None,
        shared_contacts: list[SharedContactUpdate] | None = None,
        inbound: list[BotInboundMessage] | None = None,
        bot: BaleBotInfo | None = None,
        invite_link: str = "https://ble.ir/join/test",
        join_status: JoinStatus = JoinStatus.JOINED,
    ) -> None:
        self.accounts = {self._key(phone): result for phone, result in (accounts or {}).items()}
        self.by_user_id: dict[str, BaleAccountCheckResult] = {}
        for result in self.accounts.values():
            if result.bale_user_id:
                self.by_user_id[str(result.bale_user_id)] = result
        self.shared_contacts = list(shared_contacts or [])
        self.inbound = list(inbound or [])
        self.bot = bot or BaleBotInfo(id=1, username="fake_bot", first_name="Fake", is_bot=True)
        self.exported_invite_link = invite_link
        self.default_join_status = join_status
        self.check_calls: list[tuple[str, str | None]] = []
        self.direct_invite_calls: list[tuple[str, str, str | None]] = []
        self.send_link_calls: list[tuple[str, str, str | None]] = []
        self.send_text_calls: list[tuple[str, str, dict | None]] = []
        self.join_checks: list[tuple[str, str, str | None]] = []
        self.invite_results: dict[str, DirectInviteResult] = {}
        self.link_results: dict[str, InviteLinkResult] = {}
        self.forbidden_calls: list[str] = []

    @staticmethod
    def _key(phone: str) -> str:
        return normalize_phone(phone) or phone

    def set_account(self, phone: str, result: BaleAccountCheckResult) -> None:
        self.accounts[self._key(phone)] = result
        if result.bale_user_id:
            self.by_user_id[str(result.bale_user_id)] = result

    async def verify_credentials(self) -> BaleBotInfo:
        return self.bot

    async def check_account(self, phone: str, user_id: str | None = None) -> BaleAccountCheckResult:
        self.check_calls.append((phone, user_id))
        if user_id and str(user_id) in self.by_user_id:
            return self.by_user_id[str(user_id)]
        key = self._key(phone)
        if key in self.accounts:
            return self.accounts[key]
        if user_id:
            return BaleAccountCheckResult(status=BaleAccountStatus.HAS_ACCOUNT, bale_user_id=str(user_id))
        return BaleAccountCheckResult(status=BaleAccountStatus.UNKNOWN, detail="phone_lookup_unsupported")

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        items = [item for item in self.shared_contacts if offset is None or item.update_id >= offset]
        next_offset = None
        if items:
            next_offset = max(item.update_id for item in items) + 1
        return items, next_offset

    async def fetch_inbound_messages(
        self, offset: int | None = None, timeout: int = 0
    ) -> tuple[list[BotInboundMessage], int | None]:
        items = [item for item in self.inbound if offset is None or item.update_id >= (offset or 0)]
        next_offset = None
        if items:
            next_offset = max(item.update_id for item in items) + 1
        return items, next_offset

    async def direct_invite(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> DirectInviteResult:
        self.direct_invite_calls.append((phone, group_id, user_id))
        if not user_id:
            return DirectInviteResult(status=DirectInviteStatus.SKIPPED, detail="missing_user_id")
        if user_id in self.invite_results:
            return self.invite_results[user_id]
        return DirectInviteResult(status=DirectInviteStatus.SUCCESS, detail="fake_invite")

    async def send_invite_link(
        self, phone: str, invite_link: str, user_id: str | None = None, text: str | None = None
    ) -> InviteLinkResult:
        self.send_link_calls.append((phone, invite_link, user_id))
        if not user_id:
            return InviteLinkResult(status=InviteLinkStatus.FAILED, detail="missing_user_id")
        if user_id in self.link_results:
            return self.link_results[user_id]
        return InviteLinkResult(status=InviteLinkStatus.SENT, detail="fake_send")

    async def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        self.send_text_calls.append((chat_id, text, reply_markup))

    async def export_invite_link(self, group_id: str) -> str:
        return self.exported_invite_link

    async def check_join_status(
        self, phone: str, group_id: str, user_id: str | None = None
    ) -> JoinStatusResult:
        self.join_checks.append((phone, group_id, user_id))
        if not user_id:
            return JoinStatusResult(status=JoinStatus.UNKNOWN, detail="missing_user_id")
        return JoinStatusResult(status=self.default_join_status, detail="fake_member")
