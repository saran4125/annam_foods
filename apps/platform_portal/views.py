from functools import wraps
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantUser, OwnerInvitation, PlatformAuditEvent
from . import services
from .forms import PlatformLoginForm, ActivateOwnerForm, CreateKitchenForm, InviteOwnerForm, KitchenStatusForm, KitchenFeaturesForm


def account_required(view):
    @wraps(view)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse("portal:login") + "?" + urlencode({"next": request.get_full_path()}))
        if not request.user.is_active:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def operator_required(view):
    @account_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        services.require_operator(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def root(request):
    if getattr(request, "tenant", None):
        from apps.storefront.views import home
        return home(request)
    return landing(request)


def landing(request):
    return render(request, "platform_portal/landing.html")


def _destination(user):
    return services.login_destination(user)


@never_cache
def login_view(request):
    target = request.POST.get("next", request.GET.get("next", ""))
    if not target.startswith("/platform/") or not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = ""
    if request.user.is_authenticated and request.user.is_active:
        return redirect(services.authorized_login_target(request, request.user, target) or _destination(request.user))
    form = PlatformLoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(services.authorized_login_target(request, form.get_user(), target) or _destination(form.get_user()))
    return render(request, "platform_portal/login.html", {"form": form, "next": target})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("portal:login")


@account_required
def home(request):
    kitchens = services.accessible_kitchens(request.user)
    return render(request, "platform_portal/home.html", {"kitchens": kitchens})


@operator_required
def admin_dashboard(request):
    query = request.GET.get("q", "").strip()[:100]
    kitchens = Tenant.objects.all()
    if query:
        kitchens = kitchens.filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(primary_domain__icontains=query))
    counts = {row["status"]: row["count"] for row in Tenant.objects.values("status").annotate(count=Count("pk"))}
    return render(request, "platform_portal/admin.html", {"page": Paginator(kitchens, 25).get_page(request.GET.get("page")),
        "query": query, "total": Tenant.objects.count(), "active": counts.get("active", 0), "setup": counts.get("provisioning", 0), "suspended": counts.get("suspended", 0)})


def _created(request, tenant, invitation, token):
    url = request.build_absolute_uri(reverse("portal:accept_invitation") + "?" + urlencode({"token": token}))
    response = render(request, "platform_portal/invitation_created.html", {"kitchen": tenant, "invitation": invitation, "invitation_url": url})
    response["Referrer-Policy"] = "same-origin"
    return response


@operator_required
def create_kitchen(request):
    form = CreateKitchenForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            tenant, invitation, token = services.provision_kitchen(actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, "The kitchen address or owner account changed during setup. Reload and try again.")
        else:
            return _created(request, tenant, invitation, token)
    return render(request, "platform_portal/create.html", {"form": form, "base_domain": services.base_domain()})


@account_required
def workspace(request, slug):
    kitchen = get_object_or_404(services.accessible_kitchens(request.user).select_related("config", "billing_profile"), slug=slug)
    return render(request, "platform_portal/workspace.html", {"kitchen": kitchen,
        "progress": services.onboarding_progress(kitchen), "domain": kitchen.domains.filter(is_primary=True).first(),
        "workspace_root": f"/platform/workspaces/{kitchen.slug}/"})


@operator_required
def kitchen_admin(request, slug):
    kitchen = get_object_or_404(Tenant.objects, slug=slug)
    status_form = KitchenStatusForm(initial={"status": kitchen.status})
    invite_form = InviteOwnerForm()
    features_form = KitchenFeaturesForm(initial={key: kitchen.feature(key) for key in ("website_ordering", "snacks_courier")})
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "status":
            status_form = KitchenStatusForm(request.POST)
            if status_form.is_valid():
                services.change_kitchen_status(actor=request.user, tenant=kitchen, status=status_form.cleaned_data["status"])
                messages.success(request, "Kitchen status updated.")
                return redirect("portal:kitchen_admin", slug=slug)
        elif action == "features":
            features_form = KitchenFeaturesForm(request.POST)
            if features_form.is_valid():
                services.set_kitchen_features(actor=request.user, tenant=kitchen, values=features_form.cleaned_data)
                messages.success(request, "Website feature settings saved.")
                return redirect("portal:kitchen_admin", slug=slug)
        elif action == "invite":
            invite_form = InviteOwnerForm(request.POST)
            if invite_form.is_valid():
                try:
                    invitation, token = services.invite_owner(actor=request.user, tenant=kitchen, email=invite_form.cleaned_data["email"], role=invite_form.cleaned_data["role"])
                except ValidationError as exc:
                    invite_form.add_error(None, exc)
                except IntegrityError:
                    invite_form.add_error(None, "The account changed during setup. Reload and try again.")
                else:
                    return _created(request, kitchen, invitation, token)
        else:
            raise Http404
    with tenant_context(kitchen):
        members = list(TenantUser.objects.select_related("user"))
        events = list(PlatformAuditEvent.objects.select_related("actor")[:25])
        invitations = list(OwnerInvitation.objects.select_related("user").order_by("-created_at")[:10])
    return render(request, "platform_portal/kitchen_admin.html", {"kitchen": kitchen, "status_form": status_form,
        "invite_form": invite_form, "features_form": features_form, "members": members, "events": events, "invitations": invitations})


@never_cache
def accept_invitation(request):
    token = request.POST.get("token", request.GET.get("token", ""))
    invitation = services.invitation_for_token(token)
    if not invitation:
        return render(request, "platform_portal/invitation_invalid.html", status=400)
    new_account = not invitation.user.has_usable_password()
    form = ActivateOwnerForm(invitation.user, request.POST if request.method == "POST" else None) if new_account else None
    sign_in_url = reverse("portal:login") + "?" + urlencode({"next": reverse("portal:accept_invitation") + "?" + urlencode({"token": token})})
    if request.method == "POST" and (not new_account or form.is_valid()):
        try:
            user, activated = services.accept_invitation(token=token, password=form.cleaned_data["new_password1"] if form else None, signed_in_user=request.user if request.user.is_authenticated else None)
        except ValidationError as exc:
            if form:
                form.add_error(None, exc)
            else:
                messages.error(request, " ".join(exc.messages))
        else:
            if activated:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("portal:workspace", slug=invitation.tenant.slug)
    response = render(request, "platform_portal/accept.html", {"invitation": invitation, "form": form, "token": token,
        "can_accept": request.user.is_authenticated and request.user.pk == invitation.user_id, "sign_in_url": sign_in_url})
    # Keep same-origin form Origin headers usable for CSRF while withholding
    # invitation URLs from cross-origin destinations.
    response["Referrer-Policy"] = "same-origin"
    return response


@csrf_exempt
def tenant_meta_webhook(request, slug):
    from apps.messaging.webhooks import meta_webhook
    return meta_webhook(request)


@csrf_exempt
def tenant_n8n_webhook(request, slug):
    from apps.messaging.webhooks import n8n_sync
    return n8n_sync(request)
