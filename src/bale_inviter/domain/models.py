from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bale_inviter.domain.enums import (
    BaleAccountStatus,
    DirectInviteStatus,
    InviteLinkStatus,
    JoinStatus,
)


@dataclass(slots=True)
class ContactRecord:
    name: str
    phone: str
    normalized_phone: str | None
    is_valid: bool
    bale_account_status: BaleAccountStatus = BaleAccountStatus.UNKNOWN
    direct_invite_status: DirectInviteStatus = DirectInviteStatus.NOT_STARTED
    invite_link_status: InviteLinkStatus = InviteLinkStatus.NOT_SENT
    join_status: JoinStatus = JoinStatus.UNKNOWN
    last_attempt_at: datetime | None = None
    attempt_count: int = 0
    error_message: str | None = None
    bale_user_id: str | None = None
    id: int | None = None


@dataclass(slots=True)
class ParsedContactRow:
    row_number: int
    name: str
    phone: str
    extra: dict[str, str] = field(default_factory=dict)
