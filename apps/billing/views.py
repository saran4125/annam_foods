"""Tenant-scoped staff billing portal, separate from store management."""
from functools import wraps
from uuid import uuid4
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import never_cache
from apps.orders.models import Order
from apps.owner.access import can_manage, owner_required
from apps.owner.views import OwnerLoginForm
from apps.owner.forms import BillingSettingsForm
from apps.tenancy.models import BillingProfile
from .forms import ManualOrderForm, OrderLines
from .models import Invoice
from .services import create_staff_order, confirm_payment, issue_bill, staff_catalog

CHANNELS = {"manual": "Manual billing", "web": "Website billing", "whatsapp": "WhatsApp billing"}


def staff_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "tenant", None) is None:
            raise Http404
        if not request.user.is_authenticated:
            return redirect(reverse("billing:login") + "?" + urlencode({"next": request.get_full_path()}))
        return owner_required(view)(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if getattr(request, "tenant", None) is None:
        raise Http404
    target = request.POST.get("next", request.GET.get("next", ""))
    if not target or not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse("billing:dashboard")
    if can_manage(request.user, request.tenant):
        return redirect(target)
    form = OwnerLoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if can_manage(form.get_user(), request.tenant):
            login(request, form.get_user())
            return redirect(target)
        form.add_error(None, "This account cannot access this kitchen's billing.")
    return render(request, "billing/login.html", {"form": form, "next": target})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("billing:login")


@staff_required
def dashboard(request):
    counts = {row["channel"]: row["count"] for row in Order.objects.values("channel").annotate(count=Count("pk"))}
    cards = [{"channel": key, "label": label, "count": counts.get(key, 0)} for key, label in CHANNELS.items()]
    return render(request, "billing/dashboard.html", {"cards": cards})


@staff_required
def channel_orders(request, channel):
    if channel not in CHANNELS:
        raise Http404
    query = request.GET.get("q", "").strip()[:80]
    status = request.GET.get("status", "")
    orders = Order.objects.filter(channel=channel).select_related("customer", "online_payment").prefetch_related(
        Prefetch("invoices", queryset=Invoice.objects.exclude(kind="credit_note"), to_attr="billing_invoices"))
    if query:
        orders = orders.filter(Q(order_no__icontains=query) | Q(customer__name__icontains=query) | Q(customer__phone__icontains=query) | Q(address__recipient_name__icontains=query))
    if status == "unpaid":
        orders = orders.exclude(payment_status="paid")
    elif status == "paid":
        orders = orders.filter(payment_status="paid")
    return render(request, "billing/orders.html", {"page": Paginator(orders.order_by("-placed_at"), 25).get_page(request.GET.get("page")),
        "channel": channel, "label": CHANNELS[channel], "query": query, "status": status})


@staff_required
def new_order(request):
    initial_channel = "whatsapp" if request.GET.get("channel") == "whatsapp" else "manual"
    initial = {"token": signing.dumps({"tenant": request.tenant.pk, "key": uuid4().hex}, salt="staff-billing"), "channel": initial_channel}
    initial.update({"name": request.GET.get("name", "")[:120], "phone": request.GET.get("phone", "")[:20]})
    data = request.POST if request.method == "POST" else None
    form = ManualOrderForm(data, initial=initial)
    lines = OrderLines(data, prefix="lines")
    if request.method == "POST" and form.is_valid() and lines.is_valid():
        try:
            token = signing.loads(form.cleaned_data["token"], salt="staff-billing", max_age=86400)
            if token["tenant"] != request.tenant.pk:
                raise ValueError("This order form belongs to another kitchen.")
            selected = [(line.cleaned_data["item"].pk, line.cleaned_data["quantity"], line.cleaned_data.get("meal", "")) for line in lines
                        if line.cleaned_data and not line.cleaned_data.get("DELETE")]
            order = create_staff_order(request.tenant, requested=selected, token=token["key"],
                actor=f"owner:{request.user.username}", **{k: v for k, v in form.cleaned_data.items() if k != "token"})
        except signing.SignatureExpired:
            form.add_error(None, "This form expired. Open New order again.")
        except (signing.BadSignature, KeyError):
            form.add_error(None, "Invalid order form. Open New order again.")
        except (ValueError, ValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Order saved. Confirm payment after receiving the full amount to issue its bill.")
            return redirect("billing:order", pk=order.pk)
    catalog = staff_catalog()
    groups = [("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner"), ("snacks", "Snacks"), ("other", "Other items")]
    choices = [("", "Select an item")]
    for key, label in groups:
        options = [(entry["id"], f'{entry["name"]} — ₹{entry["price"]}') for entry in catalog if key in entry["groups"]]
        if options:
            choices.append((label, options))
    for line in [*lines.forms, lines.empty_form]:
        line.fields["item"].choices = choices
    return render(request, "billing/new.html", {"form": form, "lines": lines,
        "catalog": catalog, "delivery_areas": [{"id": z.pk, "fee": str(z.delivery_fee), "minimum": str(z.min_order)}
                                                for z in form.fields["zone"].queryset]})


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    invoice = order.invoices.exclude(kind="credit_note").first()
    return render(request, "billing/order.html", {"order": order, "invoice": invoice})


@staff_required
@require_POST
def order_payment(request, pk):
    order = get_object_or_404(Order.objects, pk=pk)
    if request.POST.get("confirmed") != "yes":
        messages.error(request, "Confirm receipt of the full payment first.")
        return redirect("billing:order", pk=pk)
    try:
        order = confirm_payment(order, actor=f"owner:{request.user.username}", reference=request.POST.get("reference", "")[:120])
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("billing:order", pk=pk)
    return _issue(request, order)


def _issue(request, order):
    try:
        invoice = issue_bill(order)
    except (ValueError, ValidationError) as exc:
        messages.error(request, str(exc) + " Payment receipt, if confirmed, remains recorded.")
        return redirect("billing:order", pk=order.pk)
    return redirect("billing:bill", pk=invoice.pk)


@staff_required
@require_POST
def order_bill(request, pk):
    return _issue(request, get_object_or_404(Order.objects, pk=pk))


@staff_required
def bill_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects, pk=pk)
    return render(request, "owner/bill.html", {"invoice": invoice, "billing_portal": True, "portal_base": "billing/base.html"})


@staff_required
def settings_view(request):
    profile = get_object_or_404(BillingProfile, tenant=request.tenant)
    form = BillingSettingsForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.bill_timing = "on_payment"
        profile.save()
        messages.success(request, "Billing settings saved for all three order sources.")
        return redirect("billing:settings")
    return render(request, "owner/billing_settings.html", {"form": form, "portal_base": "billing/base.html"})


@never_cache
@staff_required
@require_GET
def customer_lookup(request):
    from .services import lookup_staff_customer
    try:
        result = lookup_staff_customer(request.GET.get('phone', ''))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse(result)
