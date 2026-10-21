from django.db import transaction
from .models import RazorpayConnection, PaymentIntent
from .provider import Razorpay, PaymentError
from .services import require_finance_owner


def save_connection(tenant, user, data):
    require_finance_owner(user, tenant)
    existing = RazorpayConnection.objects.filter(mode=data['mode']).first()
    candidate = RazorpayConnection(tenant=tenant, mode=data['mode'], key_id=data['key_id'],
        _key_secret=existing._key_secret if existing else '', _webhook_secret=existing._webhook_secret if existing else '')
    if data['key_secret']:
        candidate.key_secret = data['key_secret']
    if data['webhook_secret']:
        candidate.webhook_secret = data['webhook_secret']
    if data['enabled']:
        # Read-only credential check: saving settings never creates a charge.
        Razorpay(candidate).call('GET', 'orders?count=1')
    with transaction.atomic():
        from apps.tenancy.models import TenantConfig
        TenantConfig.objects.select_for_update().get(tenant=tenant)
        connection, _ = RazorpayConnection.objects.select_for_update().get_or_create(mode=data['mode'])
        credentials_changed = connection.key_id != candidate.key_id or bool(data['key_secret'] and connection._key_secret and data['key_secret'] != connection.key_secret)
        if connection.key_id and credentials_changed and PaymentIntent.objects.filter(
                connection=connection, state__in=['ready', 'creating', 'uncertain']).exists():
            raise PaymentError('Resolve open payments in this mode before changing its API keys.')
        if data['enabled']:
            RazorpayConnection.objects.exclude(pk=connection.pk).update(enabled=False)
        connection.key_id = candidate.key_id
        connection._key_secret = candidate._key_secret
        connection._webhook_secret = candidate._webhook_secret
        connection.enabled = data['enabled']
        connection.save()
    return connection
