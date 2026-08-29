"""Senders are the only part of messaging that knows about a specific API.

Everything above this line -- content, validation, queueing, retries, status --
belongs to the app. Swapping a sender changes how a message physically leaves;
it never changes what was said or whether we know it was said.
"""
from apps.tenancy.models import MessageProvider

from .base import SendResult, Sender
from .console import ConsoleSender
from .meta_cloud import MetaCloudSender
from .n8n import N8nSender

_SENDERS = {
    MessageProvider.META_CLOUD: MetaCloudSender,
    MessageProvider.N8N: N8nSender,
    MessageProvider.CONSOLE: ConsoleSender,
}


def sender_for(tenant) -> Sender:
    secrets = getattr(tenant, "secrets", None)
    provider = secrets.wa_provider if secrets else MessageProvider.CONSOLE
    return _SENDERS.get(provider, ConsoleSender)(tenant)


__all__ = ["Sender", "SendResult", "sender_for",
           "MetaCloudSender", "N8nSender", "ConsoleSender"]
