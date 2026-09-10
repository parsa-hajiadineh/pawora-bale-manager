from enum import Enum


class BaleAccountStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    HAS_ACCOUNT = "HAS_ACCOUNT"
    NO_ACCOUNT = "NO_ACCOUNT"
    ERROR = "ERROR"


class DirectInviteStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class InviteLinkStatus(str, Enum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    FAILED = "FAILED"


class JoinStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    JOINED = "JOINED"
    NOT_JOINED = "NOT_JOINED"


class JobType(str, Enum):
    CHECK_BALE_ACCOUNT = "CHECK_BALE_ACCOUNT"
    DIRECT_INVITE = "DIRECT_INVITE"
    SEND_INVITE_LINK = "SEND_INVITE_LINK"
    CHECK_JOIN_STATUS = "CHECK_JOIN_STATUS"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    DELAYED = "DELAYED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_JOB_STATUSES = (
    JobStatus.PENDING,
    JobStatus.DELAYED,
    JobStatus.RUNNING,
    JobStatus.RETRYING,
)

TERMINAL_JOB_STATUSES = (
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
)
