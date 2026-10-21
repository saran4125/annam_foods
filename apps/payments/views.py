import hashlib
import hmac
import json

from django.contrib import messages
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from apps.orders.models import Order
from apps.owner.access import owner_required
from apps.storefront.checkout import browser_key
from .models import RazorpayConnection, PaymentIntent, Refund
from .provider import PaymentError
from . import services


def guest_order(request, reference):
    browser = browser_key(request, create=False)
    if not browser:
        raise Http404
    return get_object_or_404(Order.objects, external_ref=f'web:{browser}:{reference.hex}')


def guest_intent(request, reference):
    order = guest_order(request, reference)
    return get_object_or_404(PaymentIntent.objects.select_related('order'), order=order)


@never_cache
@require_POST
def begin(request, reference):
    order = guest_order(request, reference)
    try:
        intent = services.start_payment(order)
        if intent.provider_order_id:
            services.reconcile_payment(intent)
    except PaymentError as exc:
        messages.error(request, str(exc))
        return redirect('storefront:checkout_complete', reference=reference)
    return redirect('storefront:payment', reference=reference)


@never_cache
@require_http_methods(['GET'])
def payment(request, reference):
    intent = guest_intent(request, reference)
    if intent.state != 'ready' or intent.order.payment_status in ('paid', 'refunded') or intent.order.status == 'cancelled':
        return redirect('storefront:checkout_complete', reference=reference)
    options = {'key': intent.key_id, 'order_id': intent.provider_order_id, 'amount': intent.amount, 'currency': intent.currency,
        'name': request.tenant.config.brand_name or request.tenant.name, 'description': intent.order.order_no,
        'prefill': {'name': intent.order.buyer_name, 'contact': intent.order.buyer_phone,
                    'email': intent.order.address.get('email', '')}}
    return render(request, 'payments/payment.html', {'intent': intent, 'options': options, 'reference': reference})


@never_cache
@require_POST
def verify(request, reference):
    intent = guest_intent(request, reference)
    try:
        services.verify_checkout(intent, request.POST.get('razorpay_order_id', ''),
            request.POST.get('razorpay_payment_id', ''), request.POST.get('razorpay_signature', ''))
    except PaymentError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    intent.order.refresh_from_db()
    return JsonResponse({'paid': intent.order.payment_status == 'paid', 'status': intent.order.payment_status})


@never_cache
@require_http_methods(['GET', 'POST'])
def status(request, reference):
    intent = guest_intent(request, reference)
    if request.method == 'POST':
        try:
            services.reconcile_payment(intent)
        except PaymentError as exc:
            return JsonResponse({'error': str(exc)}, status=503)
    intent.order.refresh_from_db()
    return JsonResponse({'paid': intent.order.payment_status == 'paid', 'status': intent.order.payment_status})


@owner_required
@never_cache
@require_http_methods(['GET', 'POST'])
def connection_settings(request):
    services.require_finance_owner(request.user, request.tenant)
    from .forms import RazorpaySettingsForm
    from .settings_services import save_connection
    mode = request.POST.get('mode', 'test') if request.method == 'POST' else request.GET.get('mode', 'test')
    if mode not in ('test', 'live'):
        mode = 'test'
    form = RazorpaySettingsForm(request.POST or None, mode=mode)
    if request.method == 'POST' and form.is_valid():
        try:
            save_connection(request.tenant, request.user, form.cleaned_data)
        except PaymentError as exc:
            form.add_error(None, str(exc))
        except RuntimeError:
            form.add_error(None, 'Secrets could not be encrypted. Check SECRETS_KEY on the server.')
        else:
            messages.success(request, 'Razorpay settings saved.' + (' Connection verified.' if form.cleaned_data['enabled'] else ' Online payment is disabled for this mode.'))
            return redirect(reverse('owner:razorpay_settings') + '?mode=' + mode)
    webhook_path = reverse('portal:razorpay_webhook', kwargs={'slug': request.tenant.slug, 'mode': mode})
    return render(request, 'payments/settings.html', {'form': form, 'mode': mode, 'webhook_url': request.build_absolute_uri(webhook_path)})


@owner_required
@never_cache
@require_POST
def refund(request, pk):
    services.require_finance_owner(request.user, request.tenant)
    order = get_object_or_404(Order.objects, pk=pk)
    intent = get_object_or_404(PaymentIntent.objects, order=order)
    try:
        if request.POST.get('action') == 'refresh':
            latest = Refund.objects.filter(intent=intent).order_by('-created_at').first()
            if latest:
                services.refresh_refund(latest)
            else:
                services.reconcile_payment(intent)
        else:
            if request.POST.get('confirmed') != 'yes':
                raise PaymentError('Confirm the full refund before submitting.')
            services.request_refund(order, actor=request.user, reason=request.POST.get('reason', ''))
    except PaymentError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, 'Razorpay status checked. Refunds are marked complete only after Razorpay confirms processing.')
    return redirect('owner:order', pk=order.pk)


@csrf_exempt
@require_POST
def webhook(request, slug, mode):
    if not request.tenant or request.tenant.slug != slug or mode not in ('test', 'live'):
        raise Http404
    connection = RazorpayConnection.objects.filter(mode=mode).first()
    if not connection or not connection._webhook_secret:
        return JsonResponse({'error': 'Payment connection not configured.'}, status=503)
    if len(request.body) > 256 * 1024:
        return JsonResponse({'error': 'Payload too large.'}, status=413)
    try:
        raw = request.body
        expected = hmac.new(connection.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        signature = request.headers.get('X-Razorpay-Signature', '')
        if not hmac.compare_digest(expected.encode(), signature.encode()):
            return JsonResponse({'error': 'Invalid signature.'}, status=403)
        body = json.loads(raw)
        event_id = request.headers.get('X-Razorpay-Event-Id') or hashlib.sha256(raw).hexdigest()
        if len(event_id) > 128:
            return JsonResponse({'error': 'Invalid event ID.'}, status=400)
        services.ingest_event(connection, event_id, body)
    except PaymentError:
        return JsonResponse({'error': 'Payment verification is pending. Retry this event.'}, status=503)
    except RuntimeError:
        return JsonResponse({'error': 'Payment credentials unavailable.'}, status=503)
    except (ValueError, TypeError, AttributeError, KeyError):
        return JsonResponse({'error': 'Invalid payment event.'}, status=400)
    return JsonResponse({'ok': True})


@never_cache
@require_http_methods(['GET'])
def customer_bill(request, reference):
    from apps.billing.models import Invoice, InvoiceKind
    order = guest_order(request, reference)
    invoice = get_object_or_404(Invoice.objects.exclude(kind=InvoiceKind.CREDIT_NOTE), order=order)
    return render(request, 'payments/customer_bill.html', {'invoice': invoice, 'reference': reference})
