"""Invoice issuance and numbering. All numbers are consumed with the bill row."""
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import MenuItem
from apps.orders.models import Order, PaymentStatus
from apps.tenancy.context import tenant_context
from apps.tenancy.models import BillingProfile, Tenant

from .models import Invoice, InvoiceKind, InvoiceSequence, InvoiceSeries

CENT = Decimal("0.01")
RUPEE = Decimal("1")


def financial_year(day=None):
    day = day or timezone.localdate()
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def _amount_words(amount):
    """Return an Indian-numbering amount phrase, including paise."""
    ones = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
            "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
            "seventeen", "eighteen", "nineteen")
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

    def under_thousand(n):
        parts = []
        if n >= 100:
            parts.extend((ones[n // 100], "hundred"))
            n %= 100
        if n >= 20:
            parts.append(tens[n // 10])
            n %= 10
        if n:
            parts.append(ones[n])
        return " ".join(parts)

    value = int(amount.quantize(CENT, rounding=ROUND_HALF_UP) * 100)
    rupees, paise = divmod(value, 100)
    if rupees == 0:
        phrase = "zero"
    else:
        chunks = []
        crore, rupees = divmod(rupees, 10_000_000)
        lakh, rupees = divmod(rupees, 100_000)
        thousand, rupees = divmod(rupees, 1000)
        if crore: chunks.append(f"{under_thousand(crore)} crore")
        if lakh: chunks.append(f"{under_thousand(lakh)} lakh")
        if thousand: chunks.append(f"{under_thousand(thousand)} thousand")
        if rupees: chunks.append(under_thousand(rupees))
        phrase = " ".join(chunks)
    result = f"{phrase} rupees"
    if paise:
        result += f" and {under_thousand(paise)} paise"
    return result.title() + " Only"


def allocate_number(tenant, series=InvoiceSeries.BILL, *, day=None):
    """Allocate within an enclosing transaction; caller must create the invoice."""
    fy = financial_year(day)
    try:
        sequence = InvoiceSequence.objects.select_for_update().get(series=series, financial_year=fy)
    except InvoiceSequence.DoesNotExist:
        try:
            with transaction.atomic():
                sequence = InvoiceSequence.objects.create(series=series, financial_year=fy, next_no=1)
        except IntegrityError:
            sequence = InvoiceSequence.objects.select_for_update().get(series=series, financial_year=fy)
    number_value = sequence.next_no
    sequence.next_no = number_value + 1
    sequence.save(update_fields=["next_no"])
    profile = tenant.billing_profile
    prefix = profile.invoice_prefix + ("C" if series == InvoiceSeries.CREDIT else "")
    number = profile.number_format.format(prefix=prefix, fy=fy, seq=number_value)
    if len(number) > 16:
        raise ValueError("Invoice number exceeds the 16-character legal limit.")
    return fy, number_value, number


def _seller_snapshot(tenant, profile):
    return {"name": profile.legal_name or tenant.name, "address": profile.address,
            "state": profile.state, "state_code": profile.state_code,
            "gstin": profile.gstin, "fssai_no": profile.fssai_no,
            "gst_mode": profile.gst_mode, "sac": profile.sac, "footer": profile.footer}


@transaction.atomic
def issue_bill(order, *, gst_details=None, force=False):
    """Issue exactly one immutable bill for an eligible order."""
    order = Order.all_tenants.select_for_update().select_related("customer", "tenant").get(pk=order.pk)
    with tenant_context(order.tenant):
        existing = Invoice.objects.filter(order=order).exclude(kind=InvoiceKind.CREDIT_NOTE).first()
        if existing:
            return existing
        if not force and order.payment_status != PaymentStatus.PAID:
            if not (order.payment_status == PaymentStatus.COD_PENDING and order.status == "delivered"):
                raise ValueError("An order must be paid or delivered COD before a bill can be issued.")
        try:
            profile = BillingProfile.objects.get(tenant=order.tenant)
        except BillingProfile.DoesNotExist as exc:
            raise ValueError("Complete billing settings before issuing a bill.") from exc
        if not force and profile.bill_timing == "on_delivery" and order.status != "delivered":
            raise ValueError("This kitchen issues bills when the order is delivered.")
        if not profile.fssai_no:
            raise ValueError("An FSSAI licence or registration number is required to issue a bill.")

        if profile.gst_mode == "regular":
            kind = InvoiceKind.TAX_INVOICE
        elif profile.gst_mode == "composition":
            kind = InvoiceKind.BILL_OF_SUPPLY
        else:
            kind = InvoiceKind.BILL

        buyer_data = {"name": order.customer.name, "phone": order.customer.phone}
        if gst_details:
            buyer_data.update(gst_details)
        elif order.buyer_gst:
            buyer_data.update(order.buyer_gst)
        else:
            buyer_data.update({"gstin": order.customer.gstin, "business_name": order.customer.business_name,
                               "billing_address": order.customer.billing_address})

        source_items = {item.pk: item for item in MenuItem.objects.filter(
            pk__in=[line.get("item_id") for line in order.items if line.get("item_id")]
        )}
        snapshots = []
        taxable_total = cgst_total = sgst_total = igst_total = Decimal("0")
        for line in order.items:
            quantity = int(line["quantity"])
            gross = Decimal(str(line["line_total"])).quantize(CENT)
            item = source_items.get(line.get("item_id"))
            rate = (item.tax_rate if item and item.tax_rate is not None else profile.tax_rate) if kind == InvoiceKind.TAX_INVOICE else Decimal("0")
            price_base = gross / (Decimal("1") + rate / 100) if profile.prices_include_tax and rate else gross
            taxable = price_base.quantize(CENT, rounding=ROUND_HALF_UP)
            tax = (gross - taxable if profile.prices_include_tax else (taxable * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP))
            place_code = str(order.address.get("state_code", ""))
            interstate = bool(place_code and profile.state_code and place_code != profile.state_code)
            cgst = Decimal("0") if interstate else (tax / 2).quantize(CENT, rounding=ROUND_HALF_UP)
            sgst = Decimal("0") if interstate else tax - cgst
            igst = tax if interstate else Decimal("0")
            snapshots.append({"description": line["name"], "sac": (item.sac if item and item.sac else profile.sac),
                              "quantity": quantity, "unit_price": line["unit_price"],
                              "taxable": str(taxable), "tax_rate": str(rate), "tax": str(tax),
                              "cgst": str(cgst), "sgst": str(sgst), "igst": str(igst)})
            taxable_total += taxable
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst

        if order.delivery_fee:
            fee = Decimal(order.delivery_fee).quantize(CENT)
            rate = profile.tax_rate if profile.delivery_fee_taxable and kind == InvoiceKind.TAX_INVOICE else Decimal("0")
            base = fee / (Decimal("1") + rate / 100) if profile.prices_include_tax and rate else fee
            base = base.quantize(CENT, rounding=ROUND_HALF_UP)
            tax = fee - base if profile.prices_include_tax and rate else (base * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            interstate = bool(order.address.get("state_code") and profile.state_code and order.address["state_code"] != profile.state_code)
            cgst = Decimal("0") if interstate else (tax / 2).quantize(CENT, rounding=ROUND_HALF_UP)
            sgst = Decimal("0") if interstate else tax - cgst
            igst = tax if interstate else Decimal("0")
            snapshots.append({"description": "Delivery fee", "sac": profile.sac, "quantity": 1,
                              "unit_price": str(fee), "taxable": str(base), "tax_rate": str(rate), "tax": str(tax),
                              "cgst": str(cgst), "sgst": str(sgst), "igst": str(igst)})
            taxable_total += base
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst

        raw_total = taxable_total + cgst_total + sgst_total + igst_total
        payable = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP) if profile.round_total else raw_total
        round_off = (payable - raw_total).quantize(CENT)
        fy, seq, number = allocate_number(order.tenant, day=timezone.localdate())
        return Invoice.objects.create(
            kind=kind, series=InvoiceSeries.BILL, number=number, financial_year=fy, sequence_no=seq,
            order=order, seller=_seller_snapshot(order.tenant, profile), buyer=buyer_data,
            lines=snapshots, taxable=taxable_total, cgst=cgst_total, sgst=sgst_total, igst=igst_total,
            round_off=round_off, total=payable, amount_words=_amount_words(payable),
            payment_mode=order.payment_mode, payment_ref=order.external_ref,
        )


@transaction.atomic
def issue_credit_note(invoice, amount=None, *, reason=""):
    """Issue an immutable full or partial credit note against an invoice."""
    original = Invoice.all_tenants.select_for_update().get(pk=invoice.pk)
    amount = Decimal(amount if amount is not None else original.total).quantize(CENT)
    if amount <= 0 or amount > original.total:
        raise ValueError("Credit amount must be positive and no greater than the original bill.")
    with tenant_context(original.tenant):
        fy, seq, number = allocate_number(original.tenant, InvoiceSeries.CREDIT)
        ratio = amount / original.total
        lines = []
        for line in original.lines:
            scaled = dict(line)
            for key in ("taxable", "tax", "cgst", "sgst", "igst"):
                scaled[key] = str((Decimal(str(line.get(key, "0"))) * ratio).quantize(CENT, rounding=ROUND_HALF_UP))
            lines.append(scaled)
        totals = {key: (getattr(original, key) * ratio).quantize(CENT, rounding=ROUND_HALF_UP)
                  for key in ("taxable", "cgst", "sgst", "igst")}
        raw = sum(totals.values(), Decimal("0"))
        rounded = raw.quantize(RUPEE, rounding=ROUND_HALF_UP) if original.round_off else raw
        return Invoice.objects.create(
            kind=InvoiceKind.CREDIT_NOTE, series=InvoiceSeries.CREDIT, number=number,
            financial_year=fy, sequence_no=seq, order=original.order, original=original,
            seller=original.seller, buyer=original.buyer, lines=lines,
            taxable=totals["taxable"], cgst=totals["cgst"], sgst=totals["sgst"], igst=totals["igst"],
            round_off=(amount - raw).quantize(CENT), total=amount,
            amount_words=_amount_words(amount), payment_mode=original.payment_mode,
            payment_ref=reason[:120],
        )


@transaction.atomic
def request_bill(*, phone, customer=None, order=None, details="", wants_gst=False, gst_details=None):
    """Create a per-phone rate-limited customer bill request."""
    from .models import InvoiceRequest

    tenant = order.tenant if order else customer.tenant if customer else None
    if tenant is None:
        raise ValueError("A tenant-owned customer or order is required.")
    with tenant_context(tenant):
        # Serialize per-kitchen request admission so concurrent webhook requests
        # cannot all pass the daily limit using the same count.
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        profile = BillingProfile.objects.get(tenant=tenant)
        today = timezone.localdate()
        count = InvoiceRequest.objects.filter(phone=phone, created_at__date=today).count()
        if count >= profile.bill_request_daily_limit:
            raise ValueError("The daily bill request limit has been reached.")
        return InvoiceRequest.objects.create(
            customer=customer, phone=phone, order=order, details=details,
            wants_gst=wants_gst, gst_details=gst_details or {},
        )


@transaction.atomic
def fulfil_request(request, order):
    """Issue the requested order bill and mark the request fulfilled atomically."""
    from .models import InvoiceRequest, InvoiceRequestStatus

    locked = InvoiceRequest.all_tenants.select_for_update().get(pk=request.pk)
    if locked.status != InvoiceRequestStatus.OPEN:
        if locked.invoice_id:
            return locked.invoice
        raise ValueError("Only open bill requests can be fulfilled.")
    if locked.tenant_id != order.tenant_id:
        raise ValueError("The bill request and order must belong to the same kitchen.")
    invoice = issue_bill(order, gst_details=locked.gst_details if locked.wants_gst else None)
    locked.invoice = invoice
    locked.order = order
    locked.status = InvoiceRequestStatus.FULFILLED
    locked.resolved_at = timezone.now()
    locked.save(update_fields=["invoice", "order", "status", "resolved_at"])
    return invoice
