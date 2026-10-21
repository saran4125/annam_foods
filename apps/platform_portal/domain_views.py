import re
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from apps.tenancy.context import tenant_context
from apps.tenancy.models import CustomDomain
from .views import account_required
from .services import accessible_kitchens
from . import domain_services as services
from .domain_network import DomainCheckError, domain_proof
from .forms import AddDomainForm


@account_required
def domains(request, slug):
    kitchen = get_object_or_404(accessible_kitchens(request.user), slug=slug)
    services.require_domain_owner(request.user, kitchen)
    form = AddDomainForm(request.POST if request.method == "POST" and request.POST.get("action") == "add" else None)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "add":
                if form.is_valid():
                    services.add_domain(actor=request.user, tenant=kitchen, hostname=form.cleaned_data["hostname"])
                    messages.success(request, "Domain added. Follow the ownership and DNS instructions below.")
                    return redirect("portal:domains", slug=slug)
            elif action in ("verify", "connect", "primary", "remove"):
                try:
                    domain_id = int(request.POST.get("domain_id", ""))
                except ValueError:
                    return HttpResponse(status=400)
                if not 0 < domain_id < 2**63:
                    return HttpResponse(status=400)
                with tenant_context(kitchen):
                    domain = get_object_or_404(CustomDomain.objects, pk=domain_id)
                method = {"verify": services.check_domain, "connect": services.connect_domain, "primary": services.make_primary, "remove": services.remove_domain}[action]
                result = method(actor=request.user, tenant=kitchen, pk=domain.pk)
                notify = messages.success if result is None or result.status == "active" else messages.info
                notify(request, result.detail if result is not None else "Domain settings updated.")
                return redirect("portal:domains", slug=slug)
            else:
                return HttpResponse(status=400)
        except (ValidationError, DomainCheckError) as exc:
            if action == "add":
                form.add_error(None, exc)
            else:
                messages.error(request, " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        except IntegrityError:
            messages.error(request, "This domain connection changed during setup. Reload the page and check its assignment.")
    with tenant_context(kitchen):
        claims = list(CustomDomain.objects.select_related("mapping"))
    labels = {"ownership_pending": "Waiting for ownership verification", "dns_pending": "Waiting for DNS", "hosting_pending": "Waiting for hosting & HTTPS", "active": "HTTPS active", "attention": "Connection needs attention"}
    for domain in claims:
        domain.status_label = labels.get(domain.status, "Setup in progress")
    try:
        target = services.destination()
    except ValidationError:
        target = ""
        messages.error(request, "Your platform administrator needs to check the hosting destination configuration.")
    return render(request, "platform_portal/domains.html", {"kitchen": kitchen, "form": form, "domains": claims,
        "existing_domains": kitchen.domains.filter(customdomain__isnull=True), "target": target,
        "apex_ipv4": settings.DOMAIN_APEX_IPV4, "connections_enabled": settings.DOMAIN_CONNECTIONS_ENABLED,
        "hosting_provider": settings.DOMAIN_HOSTING_PROVIDER})


@require_GET
@never_cache
def probe(request):
    host = request.get_host().split(":")[0].lower()
    nonce = request.GET.get("nonce", "")
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        return HttpResponse(status=404)
    domain = CustomDomain.all_tenants.filter(hostname=host, ownership_verified_at__isnull=False,
        connection_requested_at__isnull=False).first()
    if not domain or not settings.DOMAIN_CONNECTIONS_ENABLED:
        return HttpResponse(status=404)
    return JsonResponse({"proof": domain_proof(host, domain.verification_token, nonce)})


@require_GET
@never_cache
def allow_certificate(request):
    """Caddy on-demand TLS ask endpoint. No certificates for unverified claims."""
    if not settings.DOMAIN_CONNECTIONS_ENABLED or settings.DOMAIN_HOSTING_PROVIDER != "caddy":
        return HttpResponse(status=403)
    hostname = request.GET.get("domain", "").strip().lower()
    domain = CustomDomain.all_tenants.filter(hostname=hostname, ownership_verified_at__isnull=False,
        dns_verified_at__isnull=False, connection_requested_at__isnull=False).first()
    return HttpResponse(status=200 if domain else 403)
