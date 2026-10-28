"""The kitchen owner's backend at /manage/.

One small generic engine (list / edit / delete) drives every catalogue and
content resource, so adding a resource is a table entry, not five views.
Everything runs inside the request's tenant context: a pk from another kitchen
is simply a 404.
"""
import os
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlencode

from apps.messaging.models import OutboundMessage
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
    if item.fulfilment != "scheduled":
        return "Other item"
    rows = list(item.schedule.all())
    labels = list(dict.fromkeys(row.slot.label for row in rows))
    return ", ".join(labels) if labels else "Not assigned"



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
    """The single store-management sign-in; successful login stays under /manage/."""
    if getattr(request, "tenant", None) is None:
        raise Http404
    from .access import kitchen_login_target
    target = request.POST.get("next", request.GET.get("next", ""))
    destination = kitchen_login_target(request, target)
    if can_manage(request.user, request.tenant):
        return redirect(destination)
    form = OwnerLoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if can_manage(user, request.tenant):
            login(request, user)
            return redirect(destination)
        form.add_error(None, "This account can’t manage this store. Use an account assigned to this store.")
    return render(request, "owner/login.html", {"form": form, "next": destination, "photos": _login_photos()})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("owner:login")


# -- dashboard ---------------------------------------------------------------

@owner_required
def dashboard(request):
    today = timezone.localdate()
    from apps.orders.reports import daily_sales
    sales = daily_sales()
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
        "stats": stats, "todays": todays, "today": today, "sales":sales,
        "recent": orders.order_by("-placed_at")[:6], "missing_photos": missing_photos,
    })


# -- generic resources ---------------------------------------------------------

@owner_required
def resource_list(request, key):
    res = _resource(key)
    qs = res.model.objects.all()
    menu, menu_ui = None, {}
    if key == "dishes":
        from .menu_services import menu_selection, menu_items, menu_group_counts, menu_categories
        menu = menu_selection(request.GET)
        qs = menu_items(menu)
        counts = menu_group_counts(menu['on_date'])
        def group_url(kind, meal=""):
            params = {key: request.GET[key] for key in ("q", "status") if request.GET.get(key)}
            params["type"] = kind
            if kind == 'scheduled':
                params['date'] = menu['on_date'].isoformat() if menu['on_date'] else 'all'
            if meal:
                params["meal"] = meal
            return reverse("owner:list", args=["dishes"]) + "?" + urlencode(params)
        tabs = [{"label": slot.label, "count": counts["slots"].get(slot.pk, 0),
                 "url": group_url("scheduled", slot.key), "selected": menu["meal"] == slot.key}
                for slot in menu["slots"]]
        if counts["unassigned"] or menu["meal"] == "unassigned":
            tabs.append({"label": "Not assigned", "count": counts["unassigned"],
                         "url": group_url("scheduled", "unassigned"), "selected": menu["meal"] == "unassigned"})
        menu_ui = {"selection": menu, "counts": counts, "tabs": tabs,
                   "meals_url": group_url("scheduled"), "other_url": group_url("courier"),
                   "title": "Other items" if menu["kind"] == "courier" else menu["label"],
                   "categories": list(menu_categories(qs))}
        if menu['kind'] == 'scheduled' and menu['slot'] and menu['on_date']:
            from apps.catalog.models import MenuDay
            plan = MenuDay.objects.filter(slot=menu['slot'], on_date=menu['on_date']).first()
            menu_ui.update(day_plan=plan, revision=plan.revision if plan else 0)
            menu_ui['choose_url'] = reverse('owner:daily_menu') + '?' + urlencode({'type': 'scheduled', 'meal': menu['meal'], 'date': menu['on_date'].isoformat()})
    if menu and menu['kind'] == 'scheduled' and menu['slot']:
        day_base = reverse('owner:list', args=['dishes'])
        base_params = {'type': 'scheduled', 'meal': menu['meal']}
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        menu_ui.update(date_input=(menu['on_date'] or timezone.localdate()).isoformat(),
            selected_today=menu['on_date'] == today,
            selected_tomorrow=menu['on_date'] == tomorrow,
            selected_all=menu['on_date'] is None,
            today_url=day_base + '?' + urlencode({**base_params, 'date': today.isoformat()}),
            tomorrow_url=day_base + '?' + urlencode({**base_params, 'date': tomorrow.isoformat()}),
            all_url=day_base + '?' + urlencode({**base_params, 'date': 'all'}))
    columns = [column for column in res.columns if not (menu_ui.get('choose_url') and column[1] == 'category')]
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
        if menu and (param == "type" or (menu_ui.get('choose_url') and param == 'category')):
            continue
        value = request.GET.get(param, "")
        opts = [(c.pk, c.name) for c in menu_ui["categories"]] if menu and param == "category" else choices()
        if value and str(value) in {str(v) for v, _ in opts}:
            qs = qs.filter(**{lookup: (value == "1") if lookup == "active" else value})
            active_filters[param] = value
        filter_ui.append({"param": param, "label": label, "options": opts, "value": value})
    if key == "dishes":
        qs = qs.select_related("category").prefetch_related("schedule__slot")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return_url = request.get_full_path()
    def action_url(name, pk=None):
        url = reverse(name, args=[key, pk] if pk is not None else [key])
        if not menu:
            return url
        params = {"type": menu["kind"], "next": return_url}
        if menu["kind"] == "scheduled":
            params["meal"] = menu["meal"]
            params['date'] = menu['on_date'].isoformat() if menu['on_date'] else 'all'
        return url + "?" + urlencode(params)
    rows = [{"obj": o, "cells": [_cell(o, a, k) for _, a, k in columns],
             "edit_url": action_url("owner:edit", o.pk), "delete_url": action_url("owner:delete", o.pk)} for o in page]
    if menu and menu['on_date'] and menu['slot'] and menu['kind'] == 'scheduled':
        entries = {e.item.pk: e for e in resolve_menu(menu['on_date'], menu['slot'], include_unavailable=True, include_inactive=True)}
        for row in rows:
            for cell in row['cells']:
                if cell['kind'] == 'toggle':
                    cell['value'] = entries[row['obj'].pk].available
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "owner/list.html", {
        "res": res, "rows": rows, "page": page, "query": query, "filters": filter_ui,
        "menu_ui": menu_ui, "new_url": action_url("owner:new"),
        "add_label": ("Add item" if menu["kind"] == "courier" else "Add meal" if menu["meal"] == "unassigned" else "Add " + menu["label"].lower() + " dish") if menu else "Add " + res.singular,
        "headers": [('Available this day' if label == 'On sale' and menu_ui.get('choose_url') else label) for label, _, _ in columns], "querystring": params.urlencode(),
        "toggle_field": TOGGLE_FIELDS.get(key), "total": qs.count(),
    })


@owner_required
def resource_edit(request, key, pk=None):
    res = _resource(key)
    obj = get_object_or_404(res.model, pk=pk) if pk else None
    return_url = _safe_next(request, reverse("owner:list", args=[key]))
    form_kwargs = {}
    menu = None
    if key == "dishes" and request.GET.get("type") in ("scheduled", "courier"):
        from .menu_services import menu_selection
        menu = menu_selection(request.GET)
        group_params = {"type": menu["kind"]}
        if menu["kind"] == "scheduled":
            group_params["meal"] = menu["meal"]
            group_params['date'] = menu['on_date'].isoformat() if menu['on_date'] else 'all'
        return_url = _safe_next(request, reverse("owner:list", args=[key]) + "?" + urlencode(group_params))
        form_kwargs["menu_slot"] = menu["slot"] if menu["kind"] == "scheduled" else None
        form_kwargs['menu_date'] = menu['on_date'] if menu['slot'] and menu['kind'] == 'scheduled' else None
        if obj is None:
            form_kwargs["initial"] = {"fulfilment": menu["kind"]}
    form = res.form(request.POST or None, request.FILES or None, instance=obj, **form_kwargs)
    next_query = {"next": return_url}
    if menu:
        next_query.update(type=menu["kind"], meal=menu["meal"], date=menu['on_date'].isoformat() if menu['on_date'] else 'all')
    form_query = "?" + urlencode(next_query)
    if request.method == "POST" and form.is_valid():
        try:
            saved = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Saved “{saved}”.")
            if "save_add" in request.POST:
                return redirect(reverse("owner:new", args=[key]) + (form_query if menu else ""))
            return redirect(return_url)
    return render(request, "owner/form.html", {"res": res, "form": form, "obj": obj,
        "return_url": return_url, "menu_selection": menu,
        "entry_label": "item" if menu and menu["kind"] == "courier" else res.singular,
        "delete_url": reverse("owner:delete", args=[key, obj.pk]) + form_query if obj else ""})


@owner_required
def resource_delete(request, key, pk):
    res = _resource(key)
    obj = get_object_or_404(res.model, pk=pk)
    return_url = _safe_next(request, reverse("owner:list", args=[key]))
    back_params = {"next": return_url}
    selected = None
    if key == "dishes" and request.GET.get("type") in ("scheduled", "courier"):
        from .menu_services import menu_selection
        selected = menu_selection(request.GET)
        back_params.update(type=selected["kind"], meal=selected["meal"], date=selected['on_date'].isoformat() if selected['on_date'] else 'all')
    edit_url = reverse("owner:edit", args=[key, pk]) + "?" + urlencode(back_params)
    day_selection = selected if selected and selected['kind'] == 'scheduled' and selected['slot'] and selected['on_date'] else None
    day_revision = 0
    if day_selection:
        from apps.catalog.models import MenuDay
        plan = MenuDay.objects.filter(slot=selected['slot'], on_date=selected['on_date']).first()
        day_revision = plan.revision if plan else 0
    if request.method == "POST":
        if day_selection:
            from apps.catalog.daily_menus import set_daily_availability
            try:
                set_daily_availability(slot=selected['slot'], on_date=selected['on_date'], item=obj, available=False,
                                       revision=int(request.POST['day_revision']))
            except (ValidationError, ValueError, KeyError) as exc:
                messages.error(request, ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'Reload the menu and try again.')
            else:
                messages.success(request, f'“{obj}” removed from {selected["on_date"]:%A, %d %B} {selected["label"].lower()}. Other dates are unchanged.')
            return redirect(return_url)
        name = str(obj)
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, f"“{name}” is still in use (for example, products are filed under it). "
                                    "Move or delete those first, or just hide it.")
            return redirect(edit_url)
        messages.success(request, f"Deleted “{name}”.")
        return redirect(return_url)
    return render(request, "owner/confirm_delete.html", {"res": res, "obj": obj, "return_url": return_url, "day_selection": day_selection, "day_revision": day_revision,
        "edit_url": edit_url})


@owner_required
@require_POST
def resource_toggle(request, key, pk):
    """One-tap on/off (on sale, visible, published) straight from the list."""
    res = _resource(key)
    field_name = TOGGLE_FIELDS.get(key)
    if not field_name:
        raise Http404
    obj = get_object_or_404(res.model, pk=pk)
    if key == 'dishes' and request.POST.get('menu_date'):
        from .menu_services import menu_selection
        from apps.catalog.daily_menus import set_daily_availability
        selected = menu_selection({'type': 'scheduled', 'meal': request.POST.get('menu_meal'), 'date': request.POST['menu_date']})
        if not selected['slot'] or not selected['on_date'] or request.POST.get('enabled') not in ('0', '1'):
            raise Http404
        try:
            revision = int(request.POST['revision'])
            set_daily_availability(slot=selected['slot'], on_date=selected['on_date'], item=obj,
                                   available=request.POST['enabled'] == '1', revision=revision)
        except (ValidationError, ValueError, KeyError) as exc:
            messages.error(request, ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'Reload the menu and try again.')
        else:
            messages.success(request, f'“{obj}” availability updated for {selected["on_date"]:%A, %d %B} only.')
        return redirect(_safe_next(request, reverse('owner:list', args=[key])))
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
    from .order_groups import grouped_orders, label_orders
    qs, groups = grouped_orders(qs, selected=request.GET.get("meal_group", "all"), query=query, status=status)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    label_orders(page.object_list)
    return render(request, "owner/orders.html", {
        "page": page, "statuses": OrderStatus.choices, "status": status, "query": query, **groups,
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
        "order": order, "courier_charge":getattr(order,"courier_charge",None), "courier_notices":OutboundMessage.objects.filter(dedupe_key__startswith=f"courier:{order.pk}:"), "next_steps": next_steps, "events": order.events.all(),
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
def checkout_settings(request):
    from apps.delivery.checkout import save_checkout_settings
    form = forms.CheckoutSettingsForm(request.POST or None, config=request.tenant.config)
    if request.method == 'POST' and form.is_valid():
        save_checkout_settings(request.tenant, form.cleaned_data['settings'])
        messages.success(request, 'Checkout and courier delivery settings saved.')
        return redirect('owner:checkout_settings')
    return render(request, 'owner/checkout_settings.html', {'form': form})


@owner_required
@never_cache
def daily_menu(request):
    from .menu_services import menu_selection
    from apps.catalog.models import MenuDay
    from apps.catalog.daily_menus import save_daily_menu
    selected = menu_selection(request.GET)
    if selected['kind'] != 'scheduled' or not selected['slot'] or not selected['on_date']:
        raise Http404
    plan = MenuDay.objects.filter(slot=selected['slot'], on_date=selected['on_date']).first()
    entries = resolve_menu(selected['on_date'], selected['slot'], include_unavailable=True, include_inactive=True)
    form = forms.DailyMenuForm(request.POST if request.method == 'POST' else None,
        selected=[e.item.pk for e in entries if e.available], revision=plan.revision if plan else 0)
    return_url = reverse('owner:list', args=['dishes']) + '?' + urlencode({
        'type': 'scheduled', 'meal': selected['meal'], 'date': selected['on_date'].isoformat()})
    if request.method == 'POST' and form.is_valid():
        try:
            save_daily_menu(slot=selected['slot'], on_date=selected['on_date'],
                item_ids=[item.pk for item in form.cleaned_data['items']], revision=form.cleaned_data['revision'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'{selected["on_date"]:%A, %d %B} {selected["label"].lower()} menu saved. Other dates are unchanged.')
            return redirect(return_url)
    return render(request, 'owner/daily_menu.html', {'form': form, 'selection': selected, 'return_url': return_url, 'plan': plan})
