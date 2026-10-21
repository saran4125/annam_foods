from django import template
from apps.payments.models import PaymentIntent, Refund
register = template.Library()


@register.simple_tag
def payment_summary(order):
    intent = PaymentIntent.objects.filter(order=order).first()
    if not intent:
        return None
    return {'intent': intent, 'refund': Refund.objects.filter(intent=intent).order_by('-created_at').first()}
