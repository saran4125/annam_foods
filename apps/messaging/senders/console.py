import logging

from .base import SendResult

log = logging.getLogger("messaging")


class ConsoleSender:
    """Development and tests. Logs instead of sending, and always succeeds."""

    def __init__(self, tenant):
        self.tenant = tenant

    def send(self, message) -> SendResult:
        log.info(
            "[whatsapp:%s] -> %s  %s",
            self.tenant.slug, message.to_phone, message.payload,
        )
        return SendResult.sent(f"console-{message.pk}")
