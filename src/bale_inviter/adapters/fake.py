"""In-memory Bale adapter for tests. Does not call the network."""

from __future__ import annotations

from bale_inviter.adapters.bale import (
    BaleAccountCheckResult,
    BaleAdapter,
    BaleBotInfo,
    DirectInviteResult,
    InviteLinkResult,
    JoinStatusResult,
    SharedContactUpdate,
    UnimplementedBaleAdapter,
)
from bale_inviter.domain.enums import BaleAccountStatus
from bale_inviter.domain.phone import normalize_phone


class FakeBaleAdapter(BaleAdapter):
    def __init__(
        self,
        accounts: dict[str, BaleAccountCheckResult] | None = None,
        shared_contacts: list[SharedContactUpdate] | None = None,
        bot: BaleBotInfo | None = None,
    ) -> None:
        self.accounts = {self._key(phone): result for phone, result in (accounts or {}).items()}
        self.by_user_id: dict[str, BaleAccountCheckResult] = {}
        for result in self.accounts.values():
            if result.bale_user_id:
                self.by_user_id[str(result.bale_user_id)] = result
        self.shared_contacts = list(shared_contacts or [])
        self.bot = bot or BaleBotInfo(id=1, username="fake_bot", first_name="Fake", is_bot=True)
        self.check_calls: list[tuple[str, str | None]] = []
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
            return BaleAccountCheckResult(status=BaleAccountStatus.NO_ACCOUNT, detail="fake_not_found")
        return BaleAccountCheckResult(status=BaleAccountStatus.UNKNOWN, detail="phone_lookup_unsupported")

    async def fetch_shared_contacts(self, offset: int | None = None) -> tuple[list[SharedContactUpdate], int | None]:
        items = [item for item in self.shared_contacts if offset is None or item.update_id >= offset]
        next_offset = None
        if items:
            next_offset = max(item.update_id for item in items) + 1
        return items, next_offset

    async def direct_invite(self, phone: str, group_id: str) -> DirectInviteResult:
        self.forbidden_calls.append("direct_invite")
        return await UnimplementedBaleAdapter().direct_invite(phone, group_id)

    async def send_invite_link(self, phone: str, invite_link: str) -> InviteLinkResult:
        self.forbidden_calls.append("send_invite_link")
        return await UnimplementedBaleAdapter().send_invite_link(phone, invite_link)

    async def check_join_status(self, phone: str, group_id: str) -> JoinStatusResult:
        self.forbidden_calls.append("check_join_status")
        return await UnimplementedBaleAdapter().check_join_status(phone, group_id)
