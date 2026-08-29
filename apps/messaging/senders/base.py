from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_message_id: str = ""
    error: str = ""
    retryable: bool = True

    @classmethod
    def sent(cls, message_id: str = ""):
        return cls(ok=True, provider_message_id=message_id)

    @classmethod
    def transient(cls, error: str):
        """Network blip, rate limit, provider 5xx — worth trying again."""
        return cls(ok=False, error=error, retryable=True)

    @classmethod
    def permanent(cls, error: str):
        """Bad payload, invalid number, revoked token — retrying won't help."""
        return cls(ok=False, error=error, retryable=False)


class Sender(Protocol):
    def __init__(self, tenant): ...

    def send(self, message) -> SendResult:
        """Deliver one OutboundMessage. Must not raise; return a SendResult."""
        ...
