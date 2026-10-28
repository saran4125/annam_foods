import uuid

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.orders.models import Order
from apps.payments.services import active_connection
from apps.orders.services import OrderError
from .cart import Cart
from apps.delivery.policies import COURIER_NOTICE
from .forms import CheckoutForm
from .checkout import browser_key, checkout_quote, place_checkout, review_token, read_token, external_ref, receipt_adjustment


@never_cache
@require_http_methods(['GET', 'POST'])
def checkout(request):
    cart = Cart(request)
    browser_key(request)
    accepted_shop_order = False
    if request.method == 'POST' and request.POST.get('action') == 'place':
        try:
            token_data = read_token(request, request.POST.get('checkout_token', ''))
            accepted_shop_order = Order.objects.filter(
                external_ref=external_ref(token_data), fulfilment='courier').exists()
        except OrderError:
            pass  # Normal checkout validation reports invalid review tokens.
    form = CheckoutForm(request.POST or None, cart=cart, accepted_shop_order=accepted_shop_order,
                        initial={'pincode': cart.pincode, 'zone_id': cart.zone_id or ''})
    if request.method == 'POST' and request.POST.get('action') == 'place':
        # Replays of an already accepted review work after the cart is cleared.
        # All contact fields are still validated; no previous customer details
        # are ever loaded into this guest form.
        if form.is_valid():
            try:
                order, reference, created = place_checkout(request, cart, form.cleaned_data, request.POST.get('checkout_token', ''))
                if created:
                    cart.clear()
                return redirect('storefront:checkout_complete', reference=uuid.UUID(reference))
            except OrderError as exc:
                form.add_error(None, str(exc))
    elif request.method == 'POST' and request.POST.get('action') != 'edit' and form.is_valid():
        try:
            quote = checkout_quote(request.tenant, cart, form.cleaned_data)
            return render(request, 'storefront/checkout_review.html', {'form': form, 'quote': quote,
                'courier_notice': COURIER_NOTICE, 'checkout_token': review_token(request, quote, form.cleaned_data), 'cart': cart})
        except OrderError as exc:
            form.add_error(None, str(exc))
    if request.method == 'GET' and cart.is_empty:
        messages.info(request, 'Add items to your cart before checking out.')
        return redirect('storefront:cart')
    return render(request, 'storefront/checkout.html', {'form': form, 'cart': cart, 'courier_notice': COURIER_NOTICE, 'cart_totals': cart.totals()})


@never_cache
@require_http_methods(['GET'])
def complete(request, reference):
    browser = browser_key(request, create=False)
    if not browser:
        raise Http404
    order = get_object_or_404(Order.objects.select_related('slot'), external_ref=f'web:{browser}:{reference.hex}')
    instructions = (request.tenant.config.checkout_settings or {}).get('payment_instructions', '')
    from apps.payments.models import PaymentIntent
    from apps.billing.models import Invoice, InvoiceKind
    intent = PaymentIntent.objects.filter(order=order).first()
    return render(request, 'storefront/checkout_complete.html', {'order': order, 'courier_notice': COURIER_NOTICE, 'courier_charge':getattr(order,'courier_charge',None), 'courier_online_available': bool((request.tenant.config.checkout_settings or {}).get('courier_online_enabled')) and active_connection() is not None, 'receipt_adjustment': receipt_adjustment(order), 'payment_instructions': instructions, 'online': intent, 'reference': reference,
        'customer_invoice': Invoice.objects.filter(order=order).exclude(kind=InvoiceKind.CREDIT_NOTE).first()})
