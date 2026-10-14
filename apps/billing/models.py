from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.tenancy.managers import TenantOwnedModel


class InvoiceSeries(models.TextChoices):
    BILL = "bill", "Bill"
    CREDIT = "credit", "Credit note"


class InvoiceSequence(TenantOwnedModel):
    series = models.CharField(max_length=12, choices=InvoiceSeries.choices)
    financial_year = models.CharField(max_length=5)
    next_no = models.PositiveIntegerField(default=1)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "series", "financial_year"],
                name="uniq_invoice_sequence_fy",
            )
        ]


class InvoiceKind(models.TextChoices):
    TAX_INVOICE = "tax_invoice", "Tax invoice"
    BILL_OF_SUPPLY = "bill_of_supply", "Bill of supply"
    BILL = "bill", "Bill"
    CREDIT_NOTE = "credit_note", "Credit note"


class Invoice(TenantOwnedModel):
    kind = models.CharField(max_length=20, choices=InvoiceKind.choices)
    series = models.CharField(max_length=12, choices=InvoiceSeries.choices, default=InvoiceSeries.BILL)
    number = models.CharField(max_length=16)
    financial_year = models.CharField(max_length=5)
    sequence_no = models.PositiveIntegerField()
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True,
        related_name="invoices",
    )
    original = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="credit_notes",
    )
    seller = models.JSONField(default=dict)
    buyer = models.JSONField(default=dict)
    lines = models.JSONField(default=list)
    taxable = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    round_off = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    amount_words = models.CharField(max_length=240)
    payment_mode = models.CharField(max_length=12, blank=True)
    payment_ref = models.CharField(max_length=120, blank=True)
    pdf = models.CharField(max_length=255, blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    sent_customer_at = models.DateTimeField(null=True, blank=True)
    sent_owner_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_tenant_invoice_number"),
            models.UniqueConstraint(
                fields=["tenant", "series", "financial_year", "sequence_no"],
                name="uniq_tenant_invoice_sequence_value",
            ),
            models.UniqueConstraint(
                fields=["tenant", "order"],
                condition=models.Q(order__isnull=False) & ~models.Q(kind=InvoiceKind.CREDIT_NOTE),
                name="uniq_primary_invoice_per_order",
            ),
        ]

    IMMUTABLE_FIELDS = (
        "kind", "series", "number", "financial_year", "sequence_no", "order_id",
        "original_id", "seller", "buyer", "lines", "taxable", "cgst", "sgst",
        "igst", "round_off", "total", "amount_words", "payment_mode", "payment_ref",
    )

    def save(self, *args, **kwargs):
        if self.pk:
            old = Invoice.all_tenants.get(pk=self.pk)
            if any(getattr(old, field) != getattr(self, field) for field in self.IMMUTABLE_FIELDS):
                raise ValidationError("Issued invoice details are immutable; issue a credit note to correct them.")
        return super().save(*args, **kwargs)


class InvoiceRequestStatus(models.TextChoices):
    OPEN = "open", "Open"
    FULFILLED = "fulfilled", "Fulfilled"
    DECLINED = "declined", "Declined"


class InvoiceRequest(TenantOwnedModel):
    customer = models.ForeignKey(
        "orders.Customer", on_delete=models.PROTECT, null=True, blank=True,
        related_name="invoice_requests",
    )
    phone = models.CharField(max_length=20, db_index=True)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True,
        related_name="invoice_requests",
    )
    details = models.TextField(blank=True)
    wants_gst = models.BooleanField(default=False)
    gst_details = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, choices=InvoiceRequestStatus.choices, default=InvoiceRequestStatus.OPEN,
        db_index=True,
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, null=True, blank=True,
        related_name="requests",
    )
    reason = models.CharField(max_length=240, blank=True)
    handled_by = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]
