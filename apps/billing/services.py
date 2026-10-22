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
    from .presentation import logo_url
    return {"name": profile.legal_name or tenant.name, "address": profile.address,
            "state": profile.state, "state_code": profile.state_code,
            "gstin": profile.gstin, "fssai_no": profile.fssai_no,
            "gst_mode": profile.gst_mode, "sac": profile.sac, "footer": profile.footer,
            "logo_url": logo_url((tenant.config.theme or {}).get("billing_logo_url") or (tenant.config.theme or {}).get("logo_url", "")),
            "tagline": tenant.config.tagline}


@transaction.atomic
def issue_bill(order, *, gst_details=None, force=False):
    """Issue exactly one immutable bill for an eligible order."""
    order = Order.all_tenants.select_for_update().select_related("customer", "tenant").get(pk=order.pk)
    with tenant_context(order.tenant):
        existing = Invoice.objects.filter(order=order).exclude(kind=InvoiceKind.CREDIT_NOTE).first()
        if existing:
            return existing
        if hasattr(order, "online_payment") and order.online_payment.mode == "test":
            raise ValueError("Test payments do not issue real bills. Switch to live mode for production payments.")
        if order.payment_status != PaymentStatus.PAID:
            raise ValueError("Payment must be confirmed before issuing a bill.")
        try:
            profile = BillingProfile.objects.get(tenant=order.tenant)
        except BillingProfile.DoesNotExist as exc:
            raise ValueError("Complete billing settings before issuing a bill.") from exc
        validate_billing_profile(profile)

        # Checkout freezes tax/rounding choices with the order. Later settings
        # edits must not change what a customer already agreed to pay.
        for key, value in order.pricing.items():
            if key in ('gst_mode', 'prices_include_tax', 'round_total', 'delivery_fee_taxable'):
                setattr(profile, key, value)
            elif key == 'tax_rate':
                profile.tax_rate = Decimal(value)
        if profile.gst_mode == "regular":
            kind = InvoiceKind.TAX_INVOICE
        elif profile.gst_mode == "composition":
            kind = InvoiceKind.BILL_OF_SUPPLY
        else:
            kind = InvoiceKind.BILL

        buyer_data = {"name": order.address.get("recipient_name", order.customer.name), "phone": order.address.get("phone", order.customer.phone),
                      "delivery_address": order.address, "order_no": order.order_no,
                      "channel": order.get_channel_display(),
                      "delivery_date": str(order.delivery_date or ""),
                      "slot": order.slot.label if order.slot_id else ""}
        if gst_details:
            buyer_data.update(gst_details)
        elif order.buyer_gst:
            buyer_data.update(order.buyer_gst)
        elif order.pricing:
            # Guest checkout is B2C. An unverified phone number must never
            # import an existing customer's private GST/business identity.
            buyer_data.update({"gstin": "", "business_name": "", "billing_address": ""})
        else:
            buyer_data.update({"gstin": order.customer.gstin, "business_name": order.customer.business_name,
                               "billing_address": order.customer.billing_address})

        source_items = {item.pk: item for item in MenuItem.objects.filter(
            pk__in=[line.get("item_id") for line in order.items if line.get("item_id")]
        )}
        snapshots = []
        taxable_total = cgst_total = sgst_total = igst_total = Decimal("0")
        remaining_discount = Decimal(order.discount)
        item_total = sum((Decimal(str(line["line_total"])) for line in order.items), Decimal("0"))
        if remaining_discount < 0 or remaining_discount > item_total:
            raise ValueError("The order discount is invalid.")
        for index, line in enumerate(order.items):
            quantity = int(line["quantity"])
            gross = Decimal(str(line["line_total"])).quantize(CENT)
            discount = (remaining_discount if index == len(order.items) - 1 else
                        (Decimal(order.discount) * gross / item_total).quantize(CENT, rounding=ROUND_HALF_UP) if item_total else Decimal("0"))
            discount = min(discount, remaining_discount, gross)
            remaining_discount -= discount
            gross -= discount
            item = source_items.get(line.get("item_id"))
            rate = Decimal(line["tax_rate"]) if order.pricing and "tax_rate" in line else ((item.tax_rate if item and item.tax_rate is not None else profile.tax_rate) if kind == InvoiceKind.TAX_INVOICE else Decimal("0"))
            price_base = gross / (Decimal("1") + rate / 100) if profile.prices_include_tax and rate else gross
            taxable = price_base.quantize(CENT, rounding=ROUND_HALF_UP)
            tax = (gross - taxable if profile.prices_include_tax else (taxable * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP))
            place_code = str(order.address.get("state_code", ""))
            interstate = bool(place_code and profile.state_code and place_code != profile.state_code)
            cgst = Decimal("0") if interstate else (tax / 2).quantize(CENT, rounding=ROUND_HALF_UP)
            sgst = Decimal("0") if interstate else tax - cgst
            igst = tax if interstate else Decimal("0")
            snapshots.append({"description": line["name"], "sac": line.get("sac") or (item.sac if item and item.sac else profile.sac),
                              "quantity": quantity, "unit_price": line["unit_price"],
                              "discount": str(discount), "taxable": str(taxable), "tax_rate": str(rate), "tax": str(tax),
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
        if payable != Decimal(order.total):
            raise ValueError("Bill total does not match the paid order. Check tax, rounding and order totals before issuing.")
        round_off = (payable - raw_total).quantize(CENT)
        fy, seq, number = allocate_number(order.tenant, day=timezone.localdate())
        return Invoice.objects.create(
            kind=kind, series=InvoiceSeries.BILL, number=number, financial_year=fy, sequence_no=seq,
            order=order, seller=_seller_snapshot(order.tenant, profile), buyer=buyer_data,
            lines=snapshots, taxable=taxable_total, cgst=cgst_total, sgst=sgst_total, igst=igst_total,
            round_off=round_off, total=payable, amount_words=_amount_words(payable),
            payment_mode=order.payment_mode, payment_ref=order.payment_reference or order.external_ref,
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


def validate_billing_profile(profile):
    """Validate persisted settings too, including profiles created before the owner UI."""
    import re
    missing = [label for field, label in [("legal_name", "legal business name"),
               ("address", "business address"), ("state", "state"),
               ("state_code", "state code"), ("fssai_no", "FSSAI number")]
               if not getattr(profile, field).strip()]
    if missing:
        raise ValueError("Complete Billing Settings: " + ", ".join(missing) + ".")
    if not re.fullmatch(r"[0-9]{14}", profile.fssai_no):
        raise ValueError("Enter a 14-digit FSSAI number.")
    if not re.fullmatch(r"[0-9]{2}", profile.state_code):
        raise ValueError("Enter a two-digit state code.")
    if profile.gst_mode != "unregistered":
        if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", profile.gstin):
            raise ValueError("Enter a valid GSTIN for a GST-registered business.")
        if profile.gstin[:2] != profile.state_code:
            raise ValueError("GSTIN and seller state code must match.")
    if not Decimal("0") <= profile.tax_rate <= Decimal("100"):
        raise ValueError("Tax rate must be between 0 and 100.")
    profile.full_clean()


@transaction.atomic
def confirm_payment(order, *, actor, reference=""):
    """Record staff-confirmed receipt once; settings errors never undo real payment."""
    from apps.orders.models import OrderEvent, OrderStatus
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.payment_mode == "online" and hasattr(order, "online_payment") and actor != "razorpay":
        raise ValueError("Verify this payment through Razorpay; it cannot be manually marked paid.")
    if order.payment_status == PaymentStatus.PAID:
        return order
    if order.status == OrderStatus.CANCELLED or order.payment_status == PaymentStatus.REFUNDED:
        raise ValueError("Cancelled or refunded orders cannot be marked paid.")
    order.payment_status = PaymentStatus.PAID
    order.payment_reference = reference
    order.save(update_fields=["payment_status", "payment_reference"])
    OrderEvent.objects.create(order=order, from_status=order.status, to_status=order.status,
                             actor=actor[:60], note=("Payment receipt confirmed. " + reference)[:200])
    return order


@transaction.atomic
def create_staff_order(tenant, *, name, phone, channel, payment_mode, requested,
                       token, actor, address="", zone=None):
    """Capture a phone/counter/chat booking with live prices and a retry-safe key."""
    from apps.orders.models import Channel, OrderSource, OrderEvent, PaymentMode
    from apps.orders.services import generate_order_number, get_or_create_customer
    from apps.tenancy.context import get_current_tenant
    if get_current_tenant() != tenant:
        raise ValueError("Use the kitchen's billing portal to create an order.")
    if channel not in (Channel.MANUAL, Channel.WHATSAPP):
        raise ValueError("Staff orders must be manual or WhatsApp bookings.")
    if payment_mode not in (PaymentMode.MANUAL, PaymentMode.COD):
        raise ValueError("Choose a supported payment mode.")
    # Serialize retries for a kitchen, including two submissions arriving together.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    external_ref = "billing:" + token
    existing = Order.objects.filter(external_ref=external_ref).first()
    if existing:
        return existing
    quantities = {}
    for item_id, quantity in requested:
        if not isinstance(quantity, int) or not 1 <= quantity <= 999:
            raise ValueError("Quantities must be between 1 and 999.")
        quantities[item_id] = quantities.get(item_id, 0) + quantity
    if not quantities or len(quantities) > 50 or any(q > 999 for q in quantities.values()):
        raise ValueError("Choose 1 to 50 items, with at most 999 of each.")
    items = {item.pk: item for item in MenuItem.objects.filter(pk__in=quantities, active=True)}
    if set(items) != set(quantities):
        raise ValueError("An item is unavailable. Reload the form and choose active items.")
    lines = [{"item_id": pk, "name": items[pk].name, "quantity": q,
              "unit_price": str(items[pk].price), "line_total": str(items[pk].price * q),
              "is_veg": items[pk].is_veg} for pk, q in quantities.items()]
    subtotal = sum((Decimal(line["line_total"]) for line in lines), Decimal("0"))
    fee = Decimal("0")
    snapshot = {"line1": address, "fulfilment": "Collection"}
    if zone:
        from apps.delivery.models import DeliveryZone
        zone = DeliveryZone.objects.get(pk=zone.pk, active=True)
        if not address.strip():
            raise ValueError("A delivery address is required.")
        if subtotal < zone.min_order:
            raise ValueError(f"This delivery area requires a minimum order of ₹{zone.min_order}.")
        fee = zone.delivery_fee
        snapshot = {"line1": address, "area": zone.area_name, "pincode": zone.pincode}
    total = subtotal + fee
    if total <= 0 or total >= Decimal("100000000"):
        raise ValueError("Order total must be positive and below ₹10 crore.")
    customer = get_or_create_customer(tenant, phone=phone, name=name, channel=channel)
    for _ in range(5):
        try:
            with transaction.atomic():
                order = Order.objects.create(customer=customer, order_no=generate_order_number(tenant),
                    channel=channel, source=OrderSource.OWNER if channel == Channel.MANUAL else OrderSource.WA_CHAT,
                    payment_mode=payment_mode, payment_status=PaymentStatus.COD_PENDING if payment_mode == PaymentMode.COD else PaymentStatus.PENDING,
                    items=lines, address=snapshot, subtotal=subtotal, delivery_fee=fee, total=total,
                    external_ref=external_ref)
            break
        except IntegrityError:
            continue
    else:
        raise ValueError("Could not allocate an order number. Please try again.")
    OrderEvent.objects.create(order=order, to_status=order.status, actor=actor[:60],
                              note="Booking entered by staff in billing portal.")
    return order


def staff_catalog():
    """Group active catalog choices by their configured meal schedules, not names."""
    from django.db.models import Prefetch
    from apps.catalog.models import MenuSchedule
    schedules = MenuSchedule.objects.filter(available=True, slot__active=True).select_related("slot")
    result = []
    for item in MenuItem.objects.filter(active=True).select_related("category").prefetch_related(
            Prefetch("schedule", queryset=schedules, to_attr="billing_schedules")).order_by("name"):
        groups = sorted({row.slot.key for row in item.billing_schedules
                         if row.slot.key in ("breakfast", "lunch", "dinner")}) if item.fulfilment == "scheduled" else []
        result.append({"id": item.pk, "name": item.name, "price": str(item.price),
                       "category": item.category.name if item.category else "", "groups": groups or ["other"]})
    return result
