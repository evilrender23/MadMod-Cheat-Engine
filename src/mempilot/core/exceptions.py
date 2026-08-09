"""Domain exceptions with safe, actionable user messages."""

from mempilot.i18n import t


class MemPilotError(Exception):
    """Base class for expected application errors."""

    message_key = "error.unknown"

    def user_message(self) -> str:
        """Return an actionable message in the active interface language."""
        return str(self) or t(self.message_key)


class ProcessNotFoundError(MemPilotError):
    message_key = "error.process_not_found"


class ProcessNotAllowedError(MemPilotError):
    message_key = "error.process_not_allowed"


class AccessDeniedError(MemPilotError):
    message_key = "error.access_denied"


class ProcessExitedError(MemPilotError):
    message_key = "error.process_exited"


class NotAttachedError(MemPilotError):
    message_key = "error.not_attached"


class WriteNotPermittedError(MemPilotError):
    message_key = "error.write_not_permitted"


class MemoryReadError(MemPilotError):
    message_key = "error.memory_read"


class MemoryWriteError(MemPilotError):
    message_key = "error.memory_write"


class InvalidAddressError(MemPilotError):
    message_key = "error.invalid_address"


class ValueParseError(MemPilotError):
    message_key = "error.value_parse"


class PatternError(MemPilotError):
    message_key = "error.pattern"


class ScanError(MemPilotError):
    message_key = "error.scan"


class ScanCancelled(MemPilotError):  # noqa: N818 - public contract
    message_key = "error.scan_cancelled"


class WorkspaceError(MemPilotError):
    message_key = "error.workspace"


class TrainerError(MemPilotError):
    message_key = "error.trainer"


class PolicyDenied(MemPilotError):  # noqa: N818 - public contract
    message_key = "error.policy_denied"


class ProviderError(MemPilotError):
    message_key = "error.provider"
