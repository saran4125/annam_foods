import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.core.exceptions import PermissionDenied

from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantUser, Tenant, TenantDomain, TenantStatus
from apps.orders.models import Order, OrderEvent
from apps.billing.models import Invoice
from apps.billing.services import confirm_payment, issue_bill
from apps.payments.models import RazorpayConnection, PaymentIntent, Refund, PaymentEvent
from apps.payments.provider import PaymentError
from apps.payments import services
from apps.storefront.tests.test_checkout import details, prepare, review, placedata
from apps.storefront.tests.test_storefront import HOST, kitchen, menu

KEY_SECRET = 'sandbox-key-secret-only-for-tests'
WEBHOOK_SECRET = 'sandbox-webhook-secret-only-for-tests'


@pytest.fixture
def online(client, kitchen, menu):
    with tenant_context(kitchen):
        conn = RazorpayConnection(mode='test', key_id='rzp_test_Example', enabled=True)
        conn.key_secret = KEY_SECRET
        conn.webhook_secret = WEBHOOK_SECRET
        conn.save()
    prepare(client, menu)
    data = details(payment_method='online')
    response = review(client, data)
    posted = client.post('/checkout/', placedata(response, data), HTTP_HOST=HOST)
    assert posted.status_code == 302
    with tenant_context(kitchen):
        intent = PaymentIntent.objects.select_related('order').get()
        yield SimpleNamespace(conn=conn, intent=intent, order=intent.order, receipt_url=posted['Location'], tenant=kitchen)


@pytest.fixture
def api(online):
    api = Mock()
    api.secret = KEY_SECRET
    api.create_order.side_effect = lambda intent: {'id': 'order_Example', 'receipt': intent.receipt, 'amount': intent.amount, 'currency': 'INR'}
    api.find_order.side_effect = lambda intent: {'id': 'order_Example', 'receipt': intent.receipt, 'amount': intent.amount, 'currency': 'INR'}
    api.payment.return_value = entity(online)
    api.order_payments.return_value = [entity(online)]
    api.refund.return_value = refund_entity(online)
    api.refund_status.return_value = refund_entity(online)
    api.refunds.return_value = []
    with patch('apps.payments.services._client', return_value=api):
        yield api


def entity(online, **overrides):
    return {'id': 'pay_Example', 'order_id': 'order_Example', 'amount': online.intent.amount, 'currency': 'INR',
            'status': 'captured', 'captured': True, 'amount_refunded': 0, **overrides}


def refund_entity(online, **overrides):
    return {'id': 'rfnd_Example', 'payment_id': 'pay_Example', 'amount': online.intent.amount,
            'status': 'processed', **overrides}


def ready(online):
    return services.start_payment(online.order)


def owner(online):
    user = get_user_model().objects.create_user(username='finance-owner')
    TenantUser.objects.create(user=user, role='owner')
    return user


def live(online, complete_billing=True):
    online.conn.mode = 'live'
    online.conn.key_id = 'rzp_live_Example'
    online.conn.save()
    online.intent.mode = 'live'
    online.intent.key_id = online.conn.key_id
    online.intent.save()
    if complete_billing:
        p = online.tenant.billing_profile
        p.legal_name = 'Kitchen'
        p.address = 'Kitchen Road'
        p.state, p.state_code, p.fssai_no = 'Tamil Nadu', '33', '12345678901234'
        p.save()


def webhook(client, online, body, *, mode='test', secret=WEBHOOK_SECRET, event_id='event_1'):
    raw = json.dumps(body).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(f'/platform/webhooks/{online.tenant.slug}/razorpay/{mode}/', data=raw, content_type='application/json',
        HTTP_X_RAZORPAY_SIGNATURE=signature, HTTP_X_RAZORPAY_EVENT_ID=event_id, HTTP_HOST='admin.localhost')


def test_online_order_freezes_mode_and_amount_without_contacting_razorpay(online):
    assert online.intent.mode == 'test' and online.intent.amount == 26000
    assert online.order.payment_mode == 'online' and online.order.payment_status == 'pending'
    assert online.intent.state == 'new'


def test_starting_and_retrying_reuses_one_provider_order(online, api):
    first, second = ready(online), ready(online)
    assert first.pk == second.pk and first.provider_order_id == 'order_Example'
    assert api.create_order.call_count == 1 and Order.objects.count() == 1


def test_uncertain_order_creation_reconciles_receipt_instead_of_posting_twice(online, api):
    api.create_order.side_effect = PaymentError(uncertain=True)
    with pytest.raises(PaymentError):
        ready(online)
    online.intent.refresh_from_db()
    assert online.intent.state == 'uncertain'
    intent = ready(online)
    assert intent.state == 'ready' and api.create_order.call_count == 1 and api.find_order.call_count == 1


def test_unresolved_creation_never_retries_as_a_new_financial_request(online, api):
    api.create_order.side_effect = PaymentError(uncertain=True)
    with pytest.raises(PaymentError):
        ready(online)
    api.find_order.side_effect = None
    api.find_order.return_value = None
    with pytest.raises(PaymentError):
        ready(online)
    assert api.create_order.call_count == 1


@pytest.mark.parametrize('change', [{'amount': 1}, {'currency': 'USD'}, {'receipt': 'another-order'}])
def test_provider_order_must_match_the_server_receipt_amount_and_currency(online, api, change):
    api.create_order.side_effect = lambda intent: {'id': 'order_Bad', 'receipt': intent.receipt, 'amount': intent.amount, 'currency': 'INR', **change}
    with pytest.raises(PaymentError):
        ready(online)
    online.intent.refresh_from_db()
    assert online.intent.state == 'uncertain' and not online.intent.provider_order_id


def test_verified_capture_marks_paid_once_and_test_payments_never_issue_real_bills(online, api):
    intent = ready(online)
    signature = hmac.new(KEY_SECRET.encode(), b'order_Example|pay_Example', hashlib.sha256).hexdigest()
    services.verify_checkout(intent, 'order_Example', 'pay_Example', signature)
    services.verify_checkout(intent, 'order_Example', 'pay_Example', signature)
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid' and online.order.payment_reference == 'pay_Example'
    assert OrderEvent.objects.filter(order=online.order, actor='razorpay').count() == 1
    assert not Invoice.objects.exists()
    with pytest.raises(ValueError, match='Test payments'):
        issue_bill(online.order)


@pytest.mark.parametrize('change', [{'amount': 1}, {'currency': 'USD'}, {'order_id': 'order_Other'}, {'captured': False}])
def test_payment_evidence_must_match_and_be_captured(online, api, change):
    intent = ready(online)
    with pytest.raises(PaymentError):
        services.apply_payment(intent, entity(online, **change))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'


def test_invalid_checkout_signature_does_not_fetch_or_accept_a_payment(online, api):
    intent = ready(online)
    with pytest.raises(PaymentError):
        services.verify_checkout(intent, 'order_Example', 'pay_Example', 'f' * 64)
    api.payment.assert_not_called()
    with pytest.raises(PaymentError):
        services.verify_checkout(intent, 'order_Other', 'pay_Example', 'f' * 64)
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'


def test_authorisation_is_not_capture_and_failed_payments_can_retry_same_order(online, api):
    intent = ready(online)
    services.apply_payment(intent, entity(online, status='failed', captured=False))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'failed'
    assert ready(online).provider_order_id == intent.provider_order_id
    services.apply_payment(intent, entity(online, status='authorized', captured=False))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'
    services.apply_payment(intent, entity(online))
    services.apply_payment(intent, entity(online, status='failed', captured=False))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid' and api.create_order.call_count == 1


def test_live_capture_issues_one_bill_and_replayed_capture_does_not_duplicate_it(online, api):
    live(online)
    intent = ready(online)
    services.apply_payment(intent, entity(online))
    services.apply_payment(intent, entity(online))
    assert Invoice.objects.count() == 1
    assert Invoice.objects.get().total == online.order.total


def test_incomplete_billing_settings_never_undo_a_verified_live_payment(online, api):
    live(online, complete_billing=False)
    intent = services.apply_payment(ready(online), entity(online))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid'
    assert intent.bill_error and not Invoice.objects.exists()


def test_a_captured_payment_after_cancellation_is_recorded_for_refund_review(online, api):
    intent = ready(online)
    online.order.status = 'cancelled'
    online.order.save()
    services.apply_payment(intent, entity(online))
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid' and online.order.status == 'cancelled'
    assert 'review refund' in OrderEvent.objects.filter(actor='razorpay').get().note


def test_unsigned_or_wrong_secret_webhooks_make_no_state_changes(client, online, api):
    ready(online)
    body = {'event': 'payment.captured', 'payload': {'payment': {'entity': entity(online)}}}
    assert webhook(client, online, body, secret='wrong').status_code == 403
    assert PaymentEvent.objects.count() == 0
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'
    api.payment.assert_not_called()


def test_signed_webhooks_fetch_evidence_and_deduplicate_events(client, online, api):
    ready(online)
    body = {'event': 'payment.captured', 'payload': {'payment': {'entity': entity(online, amount=1)}}}
    assert webhook(client, online, body).status_code == 200
    assert webhook(client, online, body).status_code == 200
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid' and PaymentEvent.objects.count() == 1
    assert api.payment.call_count == 1


def test_webhook_network_failures_are_retryable_and_not_marked_processed(client, online, api):
    ready(online)
    body = {'event': 'payment.captured', 'payload': {'payment': {'entity': entity(online)}}}
    api.payment.side_effect = PaymentError()
    assert webhook(client, online, body).status_code == 503
    assert not PaymentEvent.objects.exists()
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'


def test_order_paid_event_fetches_captured_payment_when_payment_entity_is_absent(client, online, api):
    ready(online)
    body = {'event': 'order.paid', 'payload': {'order': {'entity': {'id': 'order_Example'}}}}
    assert webhook(client, online, body).status_code == 200
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid'


def test_webhook_test_and_live_endpoints_are_separate(client, online, api):
    ready(online)
    body = {'event': 'payment.captured', 'payload': {'payment': {'entity': entity(online)}}}
    assert webhook(client, online, body, mode='live').status_code == 503
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'


def test_guest_payment_endpoints_are_private_and_mutations_require_csrf(client, online, api):
    ready(online)
    prefix = online.receipt_url
    assert Client().get(prefix + 'payment/', HTTP_HOST=HOST).status_code == 404
    assert Client().post(prefix + 'pay/', HTTP_HOST=HOST).status_code == 404
    secured = Client(enforce_csrf_checks=True)
    secured.cookies = client.cookies
    assert secured.post(prefix + 'verify/', {}, HTTP_HOST=HOST).status_code == 403
    assert secured.post(prefix + 'status/', {}, HTTP_HOST=HOST).status_code == 403
    assert secured.post(prefix + 'pay/', {}, HTTP_HOST=HOST).status_code == 403


def test_public_checkout_exposes_only_public_key_and_never_secrets(client, online, api):
    ready(online)
    response = client.get(online.receipt_url + 'payment/', HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b'rzp_test_Example' in response.content
    assert KEY_SECRET.encode() not in response.content and WEBHOOK_SECRET.encode() not in response.content
    assert b'Test mode' in response.content


def test_razorpay_payments_cannot_be_manually_marked_paid(online):
    with pytest.raises(ValueError, match='Razorpay'):
        confirm_payment(online.order, actor='owner:test')


def test_full_refund_is_once_and_creates_one_credit_note_for_a_live_bill(online, api):
    live(online)
    intent = services.apply_payment(ready(online), entity(online))
    actor = owner(online)
    refund = services.request_refund(online.order, actor=actor, reason='Customer cancellation')
    assert refund.state == 'processed'
    online.order.refresh_from_db()
    assert online.order.payment_status == 'refunded'
    assert Invoice.objects.filter(kind='credit_note').count() == 1
    services.apply_refund(refund, refund_entity(online))
    assert Invoice.objects.filter(kind='credit_note').count() == 1
    assert api.refund.call_count == 1
    with pytest.raises(PaymentError):
        services.request_refund(online.order, actor=actor, reason='Duplicate refund')
    assert api.refund.call_count == 1


def test_pending_refund_does_not_mark_order_refunded_until_processed(online, api):
    services.apply_payment(ready(online), entity(online))
    api.refund.return_value = refund_entity(online, status='pending')
    refund = services.request_refund(online.order, actor=owner(online), reason='Cancellation')
    online.order.refresh_from_db()
    assert refund.state == 'pending' and online.order.payment_status == 'paid'
    services.refresh_refund(refund)
    online.order.refresh_from_db()
    assert online.order.payment_status == 'refunded' and api.refund.call_count == 1


def test_uncertain_refund_is_not_submitted_twice(online, api):
    services.apply_payment(ready(online), entity(online))
    actor = owner(online)
    api.refund.side_effect = PaymentError(uncertain=True)
    with pytest.raises(PaymentError):
        services.request_refund(online.order, actor=actor, reason='Cancellation')
    assert Refund.objects.get().state == 'uncertain'
    services.request_refund(online.order, actor=actor, reason='Retry click')
    assert api.refund.call_count == 1


def test_refund_response_cannot_change_amount_or_payment(online, api):
    services.apply_payment(ready(online), entity(online))
    api.refund.return_value = refund_entity(online, payment_id='pay_Other')
    with pytest.raises(PaymentError):
        services.request_refund(online.order, actor=owner(online), reason='Cancellation')
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid'


def test_staff_cannot_request_refunds_or_access_payment_credentials(client, online, api):
    services.apply_payment(ready(online), entity(online))
    staff = get_user_model().objects.create_user(username='ordinary-staff')
    TenantUser.objects.create(user=staff, role='staff')
    client.force_login(staff)
    assert client.get('/manage/payments/razorpay/', HTTP_HOST=HOST).status_code == 403
    assert client.post(f'/manage/orders/{online.order.pk}/refund/', {'reason': 'test', 'confirmed': 'yes'}, HTTP_HOST=HOST).status_code == 403
    with pytest.raises(PermissionDenied):
        services.request_refund(online.order, actor=staff, reason='test')
    api.refund.assert_not_called()


def test_credentials_are_encrypted_and_owner_settings_never_echo_saved_secrets(client, online):
    connection = RazorpayConnection.objects.get()
    assert connection._key_secret != KEY_SECRET and connection.key_secret == KEY_SECRET
    assert connection._webhook_secret != WEBHOOK_SECRET
    client.force_login(owner(online))
    response = client.get('/manage/payments/razorpay/', HTTP_HOST=HOST)
    assert response.status_code == 200
    assert KEY_SECRET.encode() not in response.content and WEBHOOK_SECRET.encode() not in response.content
    assert b'/platform/webhooks/annam/razorpay/test/' in response.content


def test_live_mode_needs_matching_keys_explicit_confirmation_and_new_mode_secrets(client, online):
    client.force_login(owner(online))
    response = client.post('/manage/payments/razorpay/', {'mode': 'live', 'key_id': 'rzp_test_Wrong', 'enabled': 'on'}, HTTP_HOST=HOST)
    assert response.status_code == 200 and response.context['form'].errors
    assert not RazorpayConnection.objects.filter(mode='live').exists()


def test_switching_live_does_not_change_existing_test_payment_mode(client, online, api):
    from apps.payments.settings_services import save_connection
    actor = owner(online)
    with patch('apps.payments.settings_services.Razorpay'):
        save_connection(online.tenant, actor, {'mode': 'live', 'key_id': 'rzp_live_Second',
            'key_secret': 'live-secret-testing', 'webhook_secret': 'live-webhook-testing', 'enabled': True})
    intent = ready(online)
    assert intent.mode == 'test' and intent.key_id == 'rzp_test_Example'
    assert RazorpayConnection.objects.get(enabled=True).mode == 'live'


def test_refund_webhook_recovers_an_unknown_network_outcome_by_the_recorded_request(client, online, api):
    services.apply_payment(ready(online), entity(online))
    api.refund.side_effect = PaymentError(uncertain=True)
    with pytest.raises(PaymentError):
        services.request_refund(online.order, actor=owner(online), reason='Cancellation')
    refund = Refund.objects.get()
    body = {'event': 'refund.processed', 'payload': {'refund': {'entity': refund_entity(online, notes={'seer_refund': refund.pk.hex})}}}
    assert webhook(client, online, body).status_code == 200
    refund.refresh_from_db()
    online.order.refresh_from_db()
    assert refund.state == 'processed' and refund.provider_id == 'rfnd_Example'
    assert online.order.payment_status == 'refunded' and api.refund.call_count == 1


def test_duplicate_refund_click_while_submitting_does_not_start_or_disrupt_another_request(online, api):
    intent = services.apply_payment(ready(online), entity(online))
    refund = Refund.objects.create(intent=intent, amount=intent.amount, reason='In progress', actor='test', state='submitting')
    result = services.request_refund(online.order, actor=owner(online), reason='Second click')
    assert result.pk == refund.pk and result.state == 'submitting'
    api.refund.assert_not_called()


def test_failed_refund_does_not_mark_order_refunded_and_allows_a_new_attempt(online, api):
    services.apply_payment(ready(online), entity(online))
    actor = owner(online)
    api.refund.return_value = refund_entity(online, status='failed')
    first = services.request_refund(online.order, actor=actor, reason='Cancellation')
    online.order.refresh_from_db()
    assert first.state == 'failed' and online.order.payment_status == 'paid'
    api.refund.return_value = refund_entity(online, id='rfnd_Retry')
    second = services.request_refund(online.order, actor=actor, reason='Retry after confirmed failure')
    assert second.pk != first.pk and second.state == 'processed'


def test_external_partial_refund_cannot_be_refunded_a_second_time_as_a_full_refund(online, api):
    api.refunds.return_value = [refund_entity(online, amount=100)]
    intent = services.apply_payment(ready(online), entity(online, amount_refunded=100))
    assert intent.state == 'part_refunded'
    with pytest.raises(PaymentError):
        services.request_refund(online.order, actor=owner(online), reason='Cancellation')
    api.refund.assert_not_called()


def test_successful_signature_with_wrong_provider_evidence_is_rejected(client, online, api):
    ready(online)
    api.payment.return_value = entity(online, amount=1)
    sig = hmac.new(KEY_SECRET.encode(), b'order_Example|pay_Example', hashlib.sha256).hexdigest()
    result = client.post(online.receipt_url + 'verify/', {'razorpay_order_id': 'order_Example', 'razorpay_payment_id': 'pay_Example', 'razorpay_signature': sig}, HTTP_HOST=HOST)
    assert result.status_code == 400
    online.order.refresh_from_db()
    assert online.order.payment_status == 'pending'


def test_checkout_mode_is_bound_to_the_review_and_cannot_silently_switch_to_real_money(client, online, api, menu):
    from apps.payments.settings_services import save_connection
    prepare(client, menu)
    response = review(client, details(payment_method='online'))
    actor = owner(online)
    with patch('apps.payments.settings_services.Razorpay'):
        save_connection(online.tenant, actor, {'mode': 'live', 'key_id': 'rzp_live_Second',
            'key_secret': 'live-secret-testing', 'webhook_secret': 'live-webhook-testing', 'enabled': True})
    result = client.post('/checkout/', placedata(response, details(payment_method='online')), HTTP_HOST=HOST)
    assert result.status_code == 200 and b'changed' in result.content
    assert Order.objects.count() == 1


def test_tenant_and_browser_cannot_access_another_kitchens_payment_or_keys(client, online, api):
    ready(online)
    rival = Tenant.objects.create(slug='rival', name='Rival', status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=rival, hostname='rival.localhost', is_primary=True)
    assert client.get(online.receipt_url + 'payment/', HTTP_HOST='rival.localhost').status_code == 404
    staff = get_user_model().objects.create_user(username='rival-owner')
    with tenant_context(rival):
        TenantUser.objects.create(user=staff, role='owner')
    client.force_login(staff)
    assert client.get('/manage/payments/razorpay/', HTTP_HOST=HOST).status_code == 403
    assert client.post(f'/manage/orders/{online.order.pk}/refund/', {'reason': 'test', 'confirmed': 'yes'}, HTTP_HOST='rival.localhost').status_code == 404


def test_provider_adapter_never_returns_secret_values_or_raw_provider_errors():
    from io import BytesIO
    from urllib.error import HTTPError
    from apps.payments.provider import Razorpay
    connection = SimpleNamespace(key_id='rzp_test_Example', key_secret=KEY_SECRET)
    error = HTTPError('https://api.razorpay.com/v1/orders', 401, 'Denied ' + KEY_SECRET, {}, BytesIO(KEY_SECRET.encode()))
    with patch('apps.payments.provider.build_opener') as opener:
        opener.return_value.open.side_effect = error
        with pytest.raises(PaymentError) as exc:
            Razorpay(connection).call('GET', 'orders?count=1')
    assert KEY_SECRET not in str(exc.value)


def test_refund_provider_request_uses_the_same_idempotency_key_and_only_server_amount(online):
    from apps.payments.provider import Razorpay
    intent = online.intent
    intent.payment_id = 'pay_Example'
    refund = SimpleNamespace(pk=__import__('uuid').uuid4(), amount=intent.amount)
    with patch.object(Razorpay, 'call') as call:
        Razorpay(online.conn).refund(intent, refund)
    args = call.call_args.args
    assert args[0:2] == ('POST', 'payments/pay_Example/refund')
    assert args[2]['amount'] == 26000 and args[3]['X-Refund-Idempotency'] == refund.pk.hex


def test_live_customer_bill_is_available_only_in_the_purchasing_browser(client, online, api):
    live(online)
    services.apply_payment(ready(online), entity(online))
    result = client.get(online.receipt_url + 'bill/', HTTP_HOST=HOST)
    assert result.status_code == 200
    assert Invoice.objects.get().number.encode() in result.content
    assert 'no-store' in result['Cache-Control']
    assert Client().get(online.receipt_url + 'bill/', HTTP_HOST=HOST).status_code == 404


def test_pending_and_test_payments_do_not_provide_a_customer_bill(client, online, api):
    assert client.get(online.receipt_url + 'bill/', HTTP_HOST=HOST).status_code == 404
    services.apply_payment(ready(online), entity(online))
    assert client.get(online.receipt_url + 'bill/', HTTP_HOST=HOST).status_code == 404


def test_payment_refund_amount_does_not_mean_the_refund_finished_processing(online, api):
    ready(online)
    api.refunds.return_value = [refund_entity(online, status='pending')]
    intent = services.apply_payment(online.intent, entity(online, status='refunded', amount_refunded=online.intent.amount))
    online.order.refresh_from_db()
    assert intent.state == 'refund_pending' and online.order.payment_status == 'paid'
    api.refunds.return_value = [refund_entity(online, status='processed')]
    intent = services.apply_payment(intent, entity(online, status='refunded', amount_refunded=online.intent.amount))
    online.order.refresh_from_db()
    assert intent.state == 'refunded' and online.order.payment_status == 'refunded'


def test_full_refund_credits_only_the_remaining_bill_balance(online, api):
    from apps.billing.services import issue_credit_note
    live(online)
    services.apply_payment(ready(online), entity(online))
    invoice = Invoice.objects.get()
    issue_credit_note(invoice, amount=100, reason='Earlier adjustment')
    refund = services.request_refund(online.order, actor=owner(online), reason='Full cancellation')
    assert refund.state == 'processed'
    credits = Invoice.objects.filter(kind='credit_note')
    assert sum(c.total for c in credits) == invoice.total and credits.count() == 2
    services.apply_refund(refund, refund_entity(online))
    assert credits.count() == 2


def test_reconciliation_command_reads_provider_state_without_starting_new_payments_or_refunds(online, api):
    from django.core.management import call_command
    from io import StringIO
    ready(online)
    call_command('reconcile_razorpay', stdout=StringIO())
    online.order.refresh_from_db()
    assert online.order.payment_status == 'paid'
    assert api.create_order.call_count == 1
    api.refund.assert_not_called()


def test_open_payment_credentials_cannot_be_replaced_but_blank_fields_preserve_secrets(online, api):
    from apps.payments.settings_services import save_connection
    ready(online)
    actor = owner(online)
    with patch('apps.payments.settings_services.Razorpay'):
        with pytest.raises(PaymentError, match='open payments'):
            save_connection(online.tenant, actor, {'mode': 'test', 'key_id': 'rzp_test_Changed',
                'key_secret': 'different-key-secret', 'webhook_secret': '', 'enabled': True})
        save_connection(online.tenant, actor, {'mode': 'test', 'key_id': online.conn.key_id,
            'key_secret': '', 'webhook_secret': '', 'enabled': True})
    online.conn.refresh_from_db()
    assert online.conn.key_secret == KEY_SECRET and online.conn.webhook_secret == WEBHOOK_SECRET
