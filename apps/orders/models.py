"""Orders — the one record both channels write.

`Order.channel` is the whole product in a single column: a website order and a
WhatsApp order are identical rows differing only by that value, which is why
one order list, one invoice series and one set of reports can cover both.
"""
from django.db import models
from django.utils import timezone

from apps.tenancy.managers import TenantOwnedModel


class Channel(models.TextChoices):
    WEB = "web", "Website"
    WHATSAPP = "whatsapp", "WhatsApp"
    MANUAL = "manual", "Entered by the kitchen"


class OrderStatus(models.TextChoices):
    PLACED = "placed", "Placed"
    CONFIRMED = "confirmed", "Confirmed"
    PREPARING = "preparing", "Preparing"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


# The only forward moves allowed. Cancelling is handled separately because it
# is reachable from anywhere that isn't already terminal.
STATUS_FLOW = {
    OrderStatus.PLACED: [OrderStatus.CONFIRMED],
    OrderStatus.CONFIRMED: [OrderStatus.PREPARING],
    OrderStatus.PREPARING: [OrderStatus.OUT_FOR_DELIVERY],
    OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [],
    OrderStatus.CANCELLED: [],
}
TERMINAL = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Awaiting payment"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    COD_PENDING = "cod_pending", "Cash on delivery"


class PaymentMode(models.TextChoices):
    ONLINE = "online", "Online"
    COD = "cod", "Cash on delivery"
    MANUAL = "manual", "Owner recorded"


class OrderSource(models.TextChoices):
    STOREFRONT = "storefront", "Storefront"
    WA_CHAT = "wa_chat", "WhatsApp chat"
    WA_CATALOG = "wa_catalog", "WhatsApp catalog"
    OWNER = "owner", "Owner"


class Customer(TenantOwnedModel):
    """Identified by phone. No passwords — guest checkout with an OTP."""

    phone = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    business_name = models.CharField(max_length=200, blank=True)
    billing_address = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WEB)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-last_seen"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_tenant_customer_phone")
        ]

    def __str__(self):
        return f"{self.name or 'Customer'} ({self.phone})"


class Address(TenantOwnedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=40, blank=True)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    landmark = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=10)
    zone = models.ForeignKey(
        "delivery.DeliveryZone", on_delete=models.SET_NULL, null=True, blank=True
    )
    is_default = models.BooleanField(default=False)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-is_default", "id"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.line1}, {self.pincode}"

    def as_snapshot(self) -> dict:
        return {
            "label": self.label, "line1": self.line1, "line2": self.line2,
            "landmark": self.landmark, "pincode": self.pincode,
            "area": self.zone.area_name if self.zone else "",
        }


class Order(TenantOwnedModel):
    order_no = models.CharField(max_length=24, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    channel = models.CharField(max_length=12, choices=Channel.choices)
    source = models.CharField(max_length=24, choices=OrderSource.choices, default=OrderSource.STOREFRONT)
    payment_mode = models.CharField(max_length=12, choices=PaymentMode.choices, default=PaymentMode.ONLINE)
    fulfilment = models.CharField(max_length=12, choices=[("scheduled", "Scheduled"), ("courier", "Courier")], default="scheduled")
    external_ref = models.CharField(max_length=120, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    buyer_gst = models.JSONField(default=dict, blank=True)
    pricing = models.JSONField(default=dict, blank=True)  # checkout tax and rounding snapshot
    rider_name = models.CharField(max_length=120, blank=True)
    rider_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED, db_index=True
    )
    payment_status = models.CharField(
        max_length=14, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True
    )

    slot = models.ForeignKey("catalog.Slot", on_delete=models.PROTECT, null=True, blank=True)
    delivery_date = models.DateField(db_index=True, null=True, blank=True)

    # Snapshots, never foreign keys: a price change next week must not rewrite
    # last week's bill, and a customer moving house must not rewrite where a
    # past order actually went.
    items = models.JSONField(default=list)
    address = models.JSONField(default=dict)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    coupon_code = models.CharField(max_length=30, blank=True)
    placed_at = models.DateTimeField(default=timezone.now)
    cancelled_reason = models.CharField(max_length=200, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-placed_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "order_no"], name="uniq_tenant_order_no"),
            models.UniqueConstraint(
                fields=["tenant", "external_ref"],
                condition=~models.Q(external_ref=""),
                name="uniq_tenant_order_external_ref",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "delivery_date", "slot"], name="idx_order_service"),
        ]

    def __str__(self):
        return self.order_no

    @property
    def buyer_name(self):
        return self.address.get('recipient_name') or self.customer.name

    @property
    def buyer_phone(self):
        return self.address.get('phone') or self.customer.phone

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def item_count(self) -> int:
        return sum(line.get("quantity", 0) for line in self.items)


class OrderEvent(TenantOwnedModel):
    """Every status change, appended. This is the answer when a client asks
    what happened to an order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.CharField(max_length=60, help_text="customer, owner:<user>, razorpay, system")
    note = models.CharField(max_length=200, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["at", "id"]

    def __str__(self):
        return f"{self.order.order_no}: {self.from_status or '—'} → {self.to_status}"
