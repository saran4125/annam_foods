"""Tenant-owned payment records. No card, UPI or bank credentials are stored."""
import uuid
from django.db import models
from apps.tenancy.managers import TenantOwnedModel
from apps.tenancy.crypto import encrypt, decrypt


class RazorpayConnection(TenantOwnedModel):
    mode = models.CharField(max_length=4, choices=[('test', 'Test'), ('live', 'Live')])
    enabled = models.BooleanField(default=False)
    key_id = models.CharField(max_length=80, blank=True)
    _key_secret = models.TextField(blank=True)
    _webhook_secret = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    key_secret = property(lambda s: decrypt(s._key_secret), lambda s, v: setattr(s, '_key_secret', encrypt(v)))
    webhook_secret = property(lambda s: decrypt(s._webhook_secret), lambda s, v: setattr(s, '_webhook_secret', encrypt(v)))

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'mode'], name='uniq_rzp_mode'),
            models.UniqueConstraint(fields=['tenant'], condition=models.Q(enabled=True), name='uniq_rzp_active'),
        ]


class PaymentIntent(TenantOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField('orders.Order', on_delete=models.PROTECT, related_name='online_payment')
    connection = models.ForeignKey(RazorpayConnection, on_delete=models.PROTECT)
    key_id = models.CharField(max_length=80)
    mode = models.CharField(max_length=4)
    amount = models.PositiveBigIntegerField()  # integer paise, derived from Decimal order total
    currency = models.CharField(max_length=3, default='INR')
    provider_order_id = models.CharField(max_length=80, blank=True)
    payment_id = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=16, default='new')  # new/creating/uncertain/error/ready/captured/refunded
    refunded_amount = models.PositiveBigIntegerField(default=0)
    credit_note = models.ForeignKey('billing.Invoice', null=True, blank=True, on_delete=models.PROTECT)
    bill_error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def receipt(self):
        return 'sk_' + self.pk.hex

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'provider_order_id'], condition=~models.Q(provider_order_id=''), name='uniq_rzp_order'),
            models.UniqueConstraint(fields=['tenant', 'payment_id'], condition=~models.Q(payment_id=''), name='uniq_rzp_capture'),
        ]


class Refund(TenantOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.ForeignKey(PaymentIntent, on_delete=models.PROTECT, related_name='refunds')
    amount = models.PositiveBigIntegerField()
    provider_id = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=16, default='requested')
    reason = models.CharField(max_length=200)
    actor = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=['tenant', 'intent'], condition=~models.Q(state='failed'), name='uniq_rzp_active_refund')]


class PaymentEvent(TenantOwnedModel):
    mode = models.CharField(max_length=4)
    event_id = models.CharField(max_length=128)
    kind = models.CharField(max_length=60)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=['tenant', 'mode', 'event_id'], name='uniq_rzp_event')]
