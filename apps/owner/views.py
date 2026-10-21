"""The kitchen owner's backend at /manage/.

One small generic engine (list / edit / delete) drives every catalogue and
content resource, so adding a resource is a table entry, not five views.
Everything runs inside the request's tenant context: a pk from another kitchen
is simply a 404.
"""
import os
from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from apps.catalog.models import MenuCategory, MenuItem, Slot
from apps.catalog.services import resolve_menu
from apps.content.models import Banner, Page
from apps.delivery.models import DeliveryZone
from apps.orders.models import STATUS_FLOW, Order, OrderStatus
from apps.orders.services import InvalidTransition, advance_status
from apps.tenancy.models import TenantConfig

from . import forms
from .access import can_manage, owner_required


@dataclass
class Resource:
    key: str
    model: type
    form: type
    title: str
    singular: str
    columns: list           # (label, attribute or callable, kind)
    search: list = field(default_factory=list)
    filters: dict = field(default_factory=dict)   # GET param -> (label, choices callable, lookup)
    order_by: tuple = ()
    icon: str = "box"
    plural: str = ""

    def __post_init__(self):
        self.plural = self.plural or self.singular + "s"


def _yes(v):
    return "Yes" if v else "No"


def _schedule_label(item):
    rows = list(item.schedule.filter(mode="weekday").select_related("slot"))
    if item.fulfilment != "scheduled":
        return "Shop"
    if not rows:
        return "Not on menu"
    days = len({r.weekday for r in rows})
    return f"{rows[0].slot.label} · {'daily' if days == 7 else f'{days} days/wk'}"


RESOURCES = {
    "dishes": Resource(
        "dishes", MenuItem, forms.DishForm, "Dishes & products", "dish", plural="dishes",
        columns=[("", "image", "image"), ("Name", "name", "title"), ("Category", "category", "text"),
                 ("Price", "price", "money"), ("Menu", _schedule_label, "text"), ("On sale", "active", "toggle")],
        search=["name", "description"],
        filters={
            "type": ("Type", lambda: [("scheduled", "Daily meals"), ("courier", "Shop items")], "fulfilment"),
            "category": ("Category", lambda: [(c.pk, c.name) for c in MenuCategory.objects.all()], "category_id"),
            "status": ("Status", lambda: [("1", "On sale"), ("0", "Hidden")], "active"),
        },
        order_by=("-active", "category__sort", "sort", "name"), icon="dish",
    ),
    "categories": Resource(
        "categories", MenuCategory, forms.CategoryForm, "Categories", "category", plural="categories",
        columns=[("", "image", "image"), ("Name", "name", "title"), ("Inside", "parent", "text"),
                 ("Products", lambda c: c.items.count(), "text"), ("Visible", "active", "toggle")],
        search=["name", "slug"], order_by=("sort", "name"), icon="grid",
    ),
    "meals": Resource(
        "meals", Slot, forms.SlotForm, "Meal times", "meal time",
        columns=[("Meal", "label", "title"), ("Orders close", "order_cutoff", "time"),
                 ("Delivery", lambda s: f"{s.delivery_from:%H:%M}–{s.delivery_to:%H:%M}" if s.delivery_from and s.delivery_to else "—", "text"),
                 ("Active", "active", "toggle")],
        order_by=("sort",), icon="clock",
    ),
    "banners": Resource(
        "banners", Banner, forms.BannerForm, "Offer banners", "banner",
        columns=[("", "image", "image-wide"), ("Title", "title", "title"), ("Link", "link", "text"),
                 ("Showing", "active", "toggle")],
        search=["title"], order_by=("sort", "id"), icon="image",
    ),
    "pages": Resource(
        "pages", Page, forms.PageForm, "Pages", "page",
        columns=[("Title", "title", "title"), ("Address", lambda p: f"/p/{p.slug}/", "text"),
                 ("In menu", "show_in_nav", "bool"), ("Published", "published", "toggle")],
        search=["title", "body_md"], order_by=("sort", "title"), icon="page",
    ),
    "zones": Resource(
        "zones", DeliveryZone, forms.ZoneForm, "Delivery areas", "delivery area",
        columns=[("Area", "area_name", "title"), ("Pincode", "pincode", "text"),
                 ("Fee", "delivery_fee", "money"), ("Minimum", "min_order", "money"),
                 ("Delivering", "active", "toggle")],
        search=["area_name", "pincode"], order_by=("pincode", "area_name"), icon="pin",
    ),
}
TOGGLE_FIELDS = {"dishes": "active", "categories": "active", "meals": "active", "banners": "active",
                 "pages": "published", "zones": "active"}


def _resource(key):
    try:
        return RESOURCES[key]
    except KeyError:
        raise Http404


def _cell(obj, accessor, kind):
    value = accessor(obj) if callable(accessor) else getattr(obj, accessor, "")
    return {"kind": kind, "value": value}


def _safe_next(request, default):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target.startswith("/") and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return target
    return default


# -- auth --------------------------------------------------------------------

class OwnerLoginForm(AuthenticationForm):
    """Same checks as Django's, with a friendlier, less technical message."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That username or password isn’t right. Check for typos and capital letters, then try again.",
    }


def _login_photos():
    """Three distinct menu photos from the current kitchen only."""
    photos, seen = [], set()
    for item in MenuItem.objects.filter(active=True).exclude(image="").order_by("category__sort", "sort", "name"):
        if item.category_id not in seen:
            seen.add(item.category_id)
            photos.append(item)
        if len(photos) == 3:
            break
    return photos


@never_cache
def login_view(request):
    """Kitchen-domain sign-in stays local; private workspace URLs use SEER login."""
    if getattr(request, "tenant", None) is None:
        raise Http404
    from apps.platform_portal.services import management_login_url, kitchen_login_target
    target = request.POST.get("next", request.GET.get("next", ""))
    if getattr(request, "workspace_slug", None):
        return redirect(management_login_url(request, target))
    destination = kitchen_login_target(request, target)
    if can_manage(request.user, request.tenant):
        return redirect(destination)
    form = OwnerLoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if can_manage(user, request.tenant):
            login(request, user)
            return redirect(destination)
        form.add_error(None, "This account can’t manage this store. Use an account assigned to this kitchen, or sign in through the SEER platform.")
    return render(request, "owner/login.html", {"form": form, "next": destination, "photos": _login_photos()})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("portal:login" if getattr(request, "workspace_slug", None) else "owner:login")


# -- dashboard ---------------------------------------------------------------

@owner_required
def dashboard(request):
    today = timezone.localdate()
    items = MenuItem.objects.all()
    todays = []
    for slot in Slot.objects.filter(active=True):
        todays.append({"slot": slot, "entries": resolve_menu(today, slot)})
    orders = Order.objects.select_related("customer")
    stats = [
        {"label": "Dishes on sale", "value": items.filter(active=True).count(), "of": items.count(), "url": reverse("owner:list", args=["dishes"]) + "?status=1"},
        {"label": "Hidden / sold out", "value": items.filter(active=False).count(), "url": reverse("owner:list", args=["dishes"]) + "?status=0"},
        {"label": "Shop items", "value": items.filter(fulfilment="courier", active=True).count(), "url": reverse("owner:list", args=["dishes"]) + "?type=courier"},
        {"label": "Orders today", "value": orders.filter(placed_at__date=today).count(), "url": reverse("owner:orders")},
        {"label": "Orders this week", "value": orders.filter(placed_at__date__gte=today - timedelta(days=6)).count(), "url": reverse("owner:orders")},
        {"label": "Categories", "value": MenuCategory.objects.filter(active=True).count(), "url": reverse("owner:list", args=["categories"])},
    ]
    missing_photos = items.filter(active=True, image="").count()
    return render(request, "owner/dashboard.html", {
        "stats": stats, "todays": todays, "today": today,
        "recent": orders.order_by("-placed_at")[:6], "missing_photos": missing_photos,
    })


# -- generic resources ---------------------------------------------------------

@owner_required
def resource_list(request, key):
    res = _resource(key)
    qs = res.model.objects.all()
    if res.order_by:
        qs = qs.order_by(*res.order_by)
    query = request.GET.get("q", "").strip()[:80]
    if query and res.search:
        cond = Q()
        for f in res.search:
            cond |= Q(**{f"{f}__icontains": query})
        qs = qs.filter(cond)
    active_filters, filter_ui = {}, []
    for param, (label, choices, lookup) in res.filters.items():
        value = request.GET.get(param, "")
        opts = choices()
        if value and str(value) in {str(v) for v, _ in opts}:
            qs = qs.filter(**{lookup: (value == "1") if lookup == "active" else value})
            active_filters[param] = value
        filter_ui.append({"param": param, "label": label, "options": opts, "value": value})
    if key == "dishes":
        qs = qs.select_related("category").prefetch_related("schedule__slot")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    rows = [{"obj": o, "cells": [_cell(o, a, k) for _, a, k in res.columns]} for o in page]
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "owner/list.html", {
        "res": res, "rows": rows, "page": page, "query": query, "filters": filter_ui,
        "headers": [label for label, _, _ in res.columns], "querystring": params.urlencode(),
        "toggle_field": TOGGLE_FIELDS.get(key), "total": qs.count(),
    })


@owner_required
def resource_edit(request, key, pk=None):
    res = _resource(key)
    obj = get_object_or_404(res.model, pk=pk) if pk else None
    form = res.form(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Saved “{saved}”.")
        if "save_add" in request.POST:
            return redirect("owner:new", key=key)
        return redirect(_safe_next(request, reverse("owner:list", args=[key])))
    return render(request, "owner/form.html", {"res": res, "form": form, "obj": obj})


@owner_required
def resource_delete(request, key, pk):
    res = _resource(key)
    obj = get_object_or_404(res.model, pk=pk)
    if request.method == "POST":
        name = str(obj)
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, f"“{name}” is still in use (for example, products are filed under it). "
                                    "Move or delete those first, or just hide it.")
            return redirect("owner:edit", key=key, pk=pk)
        messages.success(request, f"Deleted “{name}”.")
        return redirect("owner:list", key=key)
    return render(request, "owner/confirm_delete.html", {"res": res, "obj": obj})


@owner_required
@require_POST
def resource_toggle(request, key, pk):
    """One-tap on/off (on sale, visible, published) straight from the list."""
    res = _resource(key)
    field_name = TOGGLE_FIELDS.get(key)
    if not field_name:
        raise Http404
    obj = get_object_or_404(res.model, pk=pk)
    setattr(obj, field_name, not getattr(obj, field_name))
    obj.save(update_fields=[field_name])
    state = "on" if getattr(obj, field_name) else "off"
    messages.success(request, f"“{obj}” is now {state}.")
    return redirect(_safe_next(request, reverse("owner:list", args=[key])))


# -- orders ---------------------------------------------------------------------

@owner_required
def orders(request):
    qs = Order.objects.select_related("customer", "slot", "online_payment").order_by("-placed_at")
    status = request.GET.get("status", "")
    if status in OrderStatus.values:
        qs = qs.filter(status=status)
    query = request.GET.get("q", "").strip()[:40]
    if query:
        qs = qs.filter(Q(order_no__icontains=query) | Q(customer__phone__icontains=query)
                       | Q(customer__name__icontains=query) | Q(address__recipient_name__icontains=query))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "owner/orders.html", {
        "page": page, "statuses": OrderStatus.choices, "status": status, "query": query,
    })


@owner_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "slot"), pk=pk)
    if request.method == "POST":
        try:
            advance_status(order, request.POST.get("to", ""), actor=f"owner:{request.user.username}",
                           note=request.POST.get("note", "")[:200])
            messages.success(request, f"{order.order_no} is now {order.get_status_display().lower()}.")
        except InvalidTransition as exc:
            messages.error(request, str(exc))
        return redirect("owner:order", pk=pk)
    next_steps = [] if order.is_terminal else [
        (s, OrderStatus(s).label) for s in STATUS_FLOW.get(order.status, [])]
    return render(request, "owner/order_detail.html", {
        "order": order, "next_steps": next_steps, "events": order.events.all(),
        "invoice": order.invoices.exclude(kind="credit_note").first(),
    })


# -- settings ---------------------------------------------------------------------

@owner_required
def settings_view(request):
    config = TenantConfig.objects.get(tenant=request.tenant)
    theme = dict(config.theme or {})
    sections = list(config.home_sections or [])
    hero = next((s for s in sections if isinstance(s, dict) and s.get("kind") == "hero"), {})
    features = dict(config.features or {})
    initial = {
        "brand_name": config.brand_name or request.tenant.name, "tagline": config.tagline,
        "support_phone": config.support_phone, "contact_email": theme.get("contact_email", ""),
        "brand_color": theme.get("brand", "#FF8507"),
        "announcements": "\n".join(theme.get("announcements", [])),
        "hero_kicker": hero.get("kicker", ""), "hero_title": hero.get("title", ""), "hero_body": hero.get("body", ""),
        "website_ordering": request.tenant.feature("website_ordering"),
        "snacks_courier": request.tenant.feature("snacks_courier"),
    }
    form = forms.SettingsForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        config.brand_name, config.tagline, config.support_phone = d["brand_name"], d["tagline"], d["support_phone"]
        theme.update({
            "brand": d["brand_color"], "contact_email": d["contact_email"],
            "announcements": [line.strip() for line in d["announcements"].splitlines() if line.strip()][:8],
        })
        if d.get("logo"):
            ext = os.path.splitext(d["logo"].name)[1].lower() or ".png"
            path = default_storage.save(f"brand/{request.tenant.slug}-logo{ext}", d["logo"])
            theme["logo_url"] = default_storage.url(path)
        config.theme = theme
        hero_section = {"kind": "hero", "kicker": d["hero_kicker"], "title": d["hero_title"], "body": d["hero_body"]}
        config.home_sections = [s for s in sections if not (isinstance(s, dict) and s.get("kind") == "hero")] + [hero_section]
        features.update({"website_ordering": d["website_ordering"], "snacks_courier": d["snacks_courier"]})
        config.features = features
        config.full_clean()
        config.save(update_fields=["brand_name", "tagline", "support_phone", "theme", "home_sections", "features"])
        messages.success(request, "Store settings saved.")
        return redirect("owner:settings")
    return render(request, "owner/settings.html", {"form": form, "logo": theme.get("logo_url")})


@owner_required
def billing_settings(request):
    from apps.tenancy.models import BillingProfile
    profile = get_object_or_404(BillingProfile, tenant=request.tenant)
    form = forms.BillingSettingsForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.bill_timing = "on_payment"
        profile.save()
        messages.success(request, "Billing settings saved. These details will be used for future bills.")
        return redirect("owner:billing_settings")
    return render(request, "owner/billing_settings.html", {"form": form})


@owner_required
@require_POST
def order_bill(request, pk):
    from apps.billing.services import issue_bill
    order = get_object_or_404(Order.objects, pk=pk)
    try:
        invoice = issue_bill(order)
    except (ValueError, ValidationError) as exc:
        messages.error(request, str(exc))
        return redirect("owner:order", pk=pk)
    return redirect("owner:bill", pk=invoice.pk)


@owner_required
@require_POST
def order_payment(request, pk):
    from apps.billing.services import confirm_payment, issue_bill
    order = get_object_or_404(Order.objects, pk=pk)
    if request.POST.get("confirmed") != "yes":
        messages.error(request, "Confirm that the full order payment has actually been received.")
        return redirect("owner:order", pk=pk)
    try:
        order = confirm_payment(order, actor=f"owner:{request.user.username}",
                                reference=request.POST.get("reference", "")[:120])
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("owner:order", pk=pk)
    try:
        invoice = issue_bill(order)
    except (ValueError, ValidationError) as exc:
        messages.warning(request, "Payment recorded. Bill not issued: " + str(exc))
        return redirect("owner:order", pk=pk)
    messages.success(request, "Payment confirmed and bill issued.")
    return redirect("owner:bill", pk=invoice.pk)


@owner_required
def bill_detail(request, pk):
    from apps.billing.models import Invoice
    invoice = get_object_or_404(Invoice.objects.select_related("order"), pk=pk)
    return render(request, "owner/bill.html", {"invoice": invoice})


@owner_required
@never_cache
def appearance(request):
    from apps.content.services import change_storefront_design, storefront_design
    config = TenantConfig.objects.get(tenant=request.tenant)
    state = config.storefront_design or {}
    form = forms.AppearanceForm(request.POST if request.method == "POST" else None,
                                design=storefront_design(config, draft=True), revision=state.get("revision", 0), config=config)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action in {"restore", "discard"}:
            try:
                revision = int(request.POST.get("revision", ""))
                change_storefront_design(request.tenant, action=action, revision=revision)
            except (ValidationError, ValueError) as exc:
                form.add_error(None, exc if isinstance(exc, ValidationError) else "Reload the page and try again.")
            else:
                messages.success(request, "Previous design restored." if action == "restore" else "Draft discarded.")
                return redirect("owner:appearance")
        elif form.is_valid():
            try:
                change_storefront_design(request.tenant, action=action, revision=form.cleaned_data["revision"],
                                         design=form.cleaned_data["design"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Appearance published. Customers now see this design." if action == "publish"
                                 else "Draft saved. Preview it before publishing.")
                return redirect("owner:appearance")
    preview = getattr(request, "workspace_preview_url", "/") + "?design=draft"
    from apps.content.models import StorefrontImage
    from apps.content.services import storefront_image_url
    library = [{'url': storefront_image_url(request.tenant, image), 'name': image.name}
               for image in StorefrontImage.objects.only('id', 'name').order_by('-created_at')[:100]]
    return render(request, "owner/appearance.html", {"image_library": library, "form": form, "has_draft": bool(state.get("draft")),
                  "has_previous": bool(state.get("previous")), "preview_url": preview})


@owner_required
@require_POST
@never_cache
def appearance_render(request):
    from apps.content.services import storefront_design, validate_design_images
    from apps.storefront.views import home
    from django.http import JsonResponse
    config = request.tenant.config
    form = forms.AppearanceForm(request.POST, design=storefront_design(config, draft=True), config=config)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    try:
        validate_design_images(request.tenant, form.cleaned_data['design'])
    except ValidationError as exc:
        return JsonResponse({'errors': {'__all__': [{'message': m} for m in exc.messages]}}, status=400)
    request._appearance_override = form.cleaned_data['design']
    request._appearance_canvas = True
    return home(request)


@owner_required
@require_POST
@never_cache
def appearance_upload(request):
    from apps.content.services import save_storefront_image, storefront_image_url
    from django.http import JsonResponse
    upload = request.FILES.get('image')
    if upload is None:
        return JsonResponse({'error': 'Choose a photo to upload.'}, status=400)
    try:
        image = save_storefront_image(request.tenant, upload)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
    return JsonResponse({'url': storefront_image_url(request.tenant, image), 'name': image.name}, status=201)


@owner_required
@never_cache
def checkout_settings(request):
    from apps.delivery.checkout import save_checkout_settings
    form = forms.CheckoutSettingsForm(request.POST or None, config=request.tenant.config)
    if request.method == 'POST' and form.is_valid():
        save_checkout_settings(request.tenant, form.cleaned_data['settings'])
        messages.success(request, 'Checkout and courier delivery settings saved.')
        return redirect('owner:checkout_settings')
    return render(request, 'owner/checkout_settings.html', {'form': form})
