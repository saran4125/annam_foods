"""Receipt display values derived only from the issued invoice snapshots."""
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from apps.orders.models import PaymentMode


def logo_url(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if value.startswith('media/'):
        value = '/' + value
    if not value or '\\' in value or any(ord(char) < 32 for char in value):
        return ''
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    if value.startswith('/') and not value.startswith('//') and not parsed.netloc:
        return value
    if parsed.scheme in ('https', 'http') and parsed.netloc and not parsed.username and not parsed.password:
        return value
    return ''


def receipt_details(invoice):
    seller, buyer = invoice.seller, invoice.buyer
    # New bills keep the logo at issuance. Older bills use their store's current
    # logo without rewriting any issued financial or legal information.
    image = seller.get('logo_url')
    if 'logo_url' not in seller:
        image = (invoice.tenant.config.theme or {}).get('logo_url', '')
    address = buyer.get('delivery_address') or {}
    address_lines = []
    for key in ('line1', 'line2', 'address', 'street', 'area', 'landmark'):
        value = str(address.get(key) or '').strip()
        if value and value.casefold() not in {line.casefold() for line in address_lines}:
            address_lines.append(value)
    locality = ', '.join(str(address.get(key) or '').strip() for key in ('city', 'state', 'pincode')
                         if str(address.get(key) or '').strip())
    if locality:
        address_lines.append(locality)
    lines = []
    discount = Decimal('0')
    for line in invoice.lines:
        entry = dict(line)
        entry['amount'] = Decimal(str(line['taxable'])) + Decimal(str(line['tax']))
        entry['discount_amount'] = Decimal(str(line.get('discount', '0')))
        discount += entry['discount_amount']
        lines.append(entry)
    try:
        payment = {PaymentMode.ONLINE: 'Online payment', PaymentMode.MANUAL: 'Manual payment',
                   PaymentMode.COD: 'Cash on delivery'}[PaymentMode(invoice.payment_mode)]
    except ValueError:
        payment = invoice.payment_mode
    try:
        delivery_date = date.fromisoformat(str(buyer.get('delivery_date') or ''))
    except ValueError:
        delivery_date = None
    tagline = seller.get('tagline', invoice.tenant.config.tagline)
    return {'logo_url': logo_url(image), 'tagline': tagline, 'delivery_date': delivery_date,
            'address_lines': address_lines,
            'collection': address.get('fulfilment') == 'Collection',
            'lines': lines, 'discount': discount, 'payment_label': payment,
            'is_credit': invoice.kind == 'credit_note',
            'tax_registered': seller.get('gst_mode') == 'regular'}
