from __future__ import annotations

from typing import TypeVar

from bale_inviter.domain.enums import (
    BaleAccountStatus,
    DirectInviteStatus,
    InviteLinkStatus,
    JoinStatus,
)

T = TypeVar("T")


class InvalidStatusTransition(ValueError):
    pass


BALE_ACCOUNT_TRANSITIONS: dict[BaleAccountStatus, set[BaleAccountStatus]] = {
    BaleAccountStatus.UNKNOWN: {
        BaleAccountStatus.HAS_ACCOUNT,
        BaleAccountStatus.NO_ACCOUNT,
        BaleAccountStatus.ERROR,
        BaleAccountStatus.UNKNOWN,
    },
    BaleAccountStatus.HAS_ACCOUNT: {
        BaleAccountStatus.HAS_ACCOUNT,
        BaleAccountStatus.NO_ACCOUNT,
        BaleAccountStatus.ERROR,
    },
    BaleAccountStatus.NO_ACCOUNT: {
        BaleAccountStatus.HAS_ACCOUNT,
        BaleAccountStatus.NO_ACCOUNT,
        BaleAccountStatus.ERROR,
    },
    BaleAccountStatus.ERROR: {
        BaleAccountStatus.UNKNOWN,
        BaleAccountStatus.HAS_ACCOUNT,
        BaleAccountStatus.NO_ACCOUNT,
        BaleAccountStatus.ERROR,
    },
}

DIRECT_INVITE_TRANSITIONS: dict[DirectInviteStatus, set[DirectInviteStatus]] = {
    DirectInviteStatus.NOT_STARTED: {
        DirectInviteStatus.SUCCESS,
        DirectInviteStatus.FAILED,
        DirectInviteStatus.SKIPPED,
        DirectInviteStatus.NOT_STARTED,
    },
    DirectInviteStatus.FAILED: {
        DirectInviteStatus.SUCCESS,
        DirectInviteStatus.FAILED,
        DirectInviteStatus.SKIPPED,
        DirectInviteStatus.NOT_STARTED,
    },
    DirectInviteStatus.SKIPPED: {
        DirectInviteStatus.SUCCESS,
        DirectInviteStatus.FAILED,
        DirectInviteStatus.SKIPPED,
        DirectInviteStatus.NOT_STARTED,
    },
    DirectInviteStatus.SUCCESS: {
        DirectInviteStatus.SUCCESS,
    },
}

INVITE_LINK_TRANSITIONS: dict[InviteLinkStatus, set[InviteLinkStatus]] = {
    InviteLinkStatus.NOT_SENT: {
        InviteLinkStatus.SENT,
        InviteLinkStatus.FAILED,
        InviteLinkStatus.NOT_SENT,
    },
    InviteLinkStatus.FAILED: {
        InviteLinkStatus.SENT,
        InviteLinkStatus.FAILED,
        InviteLinkStatus.NOT_SENT,
    },
    InviteLinkStatus.SENT: {
        InviteLinkStatus.SENT,
        InviteLinkStatus.FAILED,
    },
}

JOIN_STATUS_TRANSITIONS: dict[JoinStatus, set[JoinStatus]] = {
    JoinStatus.UNKNOWN: {
        JoinStatus.JOINED,
        JoinStatus.NOT_JOINED,
        JoinStatus.UNKNOWN,
    },
    JoinStatus.NOT_JOINED: {
        JoinStatus.JOINED,
        JoinStatus.NOT_JOINED,
        JoinStatus.UNKNOWN,
    },
    JoinStatus.JOINED: {
        JoinStatus.JOINED,
    },
}


def transition(current: T, new: T, allowed: dict[T, set[T]], field_name: str) -> T:
    options = allowed.get(current, set())
    if new not in options:
        raise InvalidStatusTransition(
            f"Cannot change {field_name} from {current.value} to {new.value}"
        )
    return new
