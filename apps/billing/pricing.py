"""Checkout totals use the same per-line tax and rounding rules as bills."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('.01')


def checkout_totals(tenant, lines, fee):
    profile = tenant.billing_profile
    settings = {key: getattr(profile, key) for key in
                ('gst_mode', 'prices_include_tax', 'round_total', 'delivery_fee_taxable')}
    settings['tax_rate'] = str(profile.tax_rate)
    regular = profile.gst_mode == 'regular'
    extra_tax = tax_total = Decimal('0')
    from apps.catalog.models import MenuItem
    items = {item.pk: item for item in MenuItem.objects.filter(pk__in=[line['item_id'] for line in lines])}
    for line in lines:
        item = items[line['item_id']]
        rate = (item.tax_rate if item.tax_rate is not None else profile.tax_rate) if regular else Decimal('0')
        line['tax_rate'] = str(rate)
        line['sac'] = item.sac or profile.sac
        gross = Decimal(line['line_total']).quantize(CENT)
        tax = (gross - (gross / (1 + rate / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
               if profile.prices_include_tax else (gross * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP))
        tax_total += tax
        if not profile.prices_include_tax:
            extra_tax += tax
    rate = profile.tax_rate if regular and profile.delivery_fee_taxable else Decimal('0')
    gross = fee.quantize(CENT)
    tax = (gross - (gross / (1 + rate / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
           if profile.prices_include_tax else (gross * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP))
    tax_total += tax
    if not profile.prices_include_tax:
        extra_tax += tax
    subtotal = sum((Decimal(line['line_total']) for line in lines), Decimal('0'))
    raw = subtotal + fee + extra_tax
    total = raw.quantize(Decimal('1'), rounding=ROUND_HALF_UP) if profile.round_total else raw
    return {'subtotal': subtotal, 'delivery_fee': fee, 'tax': tax_total, 'extra_tax': extra_tax,
            'round_off': total - raw, 'total': total, 'pricing': settings}
