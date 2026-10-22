from django import template
from apps.billing.presentation import receipt_details

register = template.Library()


@register.simple_tag
def bill_details(invoice):
    return receipt_details(invoice)
