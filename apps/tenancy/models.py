from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import TenantOwnedModel


class TenantStatus(models.TextChoices):
    """The suspension ladder. Order matters: each rung squeezes the owner
    harder before it ever touches his customers."""

    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"          # owner sees a banner, nothing else changes
    RESTRICTED = "restricted", "Restricted"    # backend read-only, storefront still sells
    SUSPENDED = "suspended", "Suspended"       # ordering off, owner keeps access to his data
    CANCELLED = "cancelled", "Cancelled"       # deliberate, never automatic


class MenuMode(models.TextChoices):
    DAILY = "daily", "Planned each day"
    WEEKLY = "weekly", "Planned by weekday"


class Tenant(models.Model):
    """One cloud kitchen."""

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    primary_domain = models.CharField(
        max_length=255, blank=True,
        help_text="Canonical hostname used to build absolute URLs.",
    )
    status = models.CharField(
        max_length=20, choices=TenantStatus.choices, default=TenantStatus.PROVISIONING
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def can_take_orders(self) -> bool:
        """Suspended and cancelled kitchens stop selling. Past due and
        restricted keep selling — we never punish the customers first."""
        return self.status in {
            TenantStatus.ACTIVE,
            TenantStatus.PAST_DUE,
            TenantStatus.RESTRICTED,
        }

    @property
    def backend_is_read_only(self) -> bool:
        return self.status == TenantStatus.RESTRICTED

    @property
    def shows_billing_banner(self) -> bool:
        return self.status in {
            TenantStatus.PAST_DUE,
            TenantStatus.RESTRICTED,
            TenantStatus.SUSPENDED,
        }


class TenantDomain(models.Model):
    """Every hostname that resolves to a tenant.

    A kitchen usually has two or three: the apex, www, and a temporary
    subdomain we use before their DNS is pointed at us.
    """

    # Exempt from tenant scoping: the middleware queries this table to
    # discover which tenant a request belongs to, so it cannot itself require
    # a tenant to already be in context.
    tenant_scoping_exempt = "resolves the tenant; runs before one is known"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=255, unique=True, db_index=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "hostname"]

    def __str__(self):
        return self.hostname

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower()
        return super().save(*args, **kwargs)


class TenantConfig(models.Model):
    """Everything that differs between kitchens.

    If a client asks for something new, it belongs here as a field or a
    `features` flag — never as a fork of the code.
    """

    # Exempt from tenant scoping: this is a one-to-one extension of Tenant
    # and is only ever reached as `tenant.config`, so there is no query path
    # that could cross kitchens.
    tenant_scoping_exempt = "one-to-one with Tenant; only reached via tenant.config"

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="config")

    # Presentation
    brand_name = models.CharField(max_length=120, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    theme = models.JSONField(default=dict, blank=True)  # colours, fonts, logo path
    support_phone = models.CharField(max_length=20, blank=True)

    # Operations
    timezone = models.CharField(max_length=40, default="Asia/Kolkata")
    currency = models.CharField(max_length=3, default="INR")
    menu_mode = models.CharField(
        max_length=10, choices=MenuMode.choices, default=MenuMode.DAILY
    )
    kitchen_open = models.TimeField(null=True, blank=True)
    kitchen_close = models.TimeField(null=True, blank=True)

    # Billing to the customer
    invoice_prefix = models.CharField(max_length=12, default="INV")
    invoice_next_no = models.PositiveIntegerField(default=1)
    gstin = models.CharField(max_length=20, blank=True)
    fssai_no = models.CharField(max_length=20, blank=True)

    features = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Config for {self.tenant.name}"

    def feature(self, key, default=False):
        return self.features.get(key, default)


class TenantUserRole(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    STAFF = "staff", "Staff"


class TenantUser(TenantOwnedModel):
    """Links a Django user to the kitchen they work for."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_memberships"
    )
    role = models.CharField(
        max_length=20, choices=TenantUserRole.choices, default=TenantUserRole.STAFF
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="uniq_tenant_user")
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant.name} ({self.role})"


class MessageProvider(models.TextChoices):
    """How a tenant's WhatsApp messages physically leave the building.

    The app always owns the message -- its content, validation, queueing and
    retries. This only chooses the driver for the final hop.
    """

    META_CLOUD = "meta_cloud", "Meta Cloud API (direct)"
    N8N = "n8n", "Via n8n webhook"
    CONSOLE = "console", "Console (development)"


class TenantSecrets(models.Model):
    """Per-tenant credentials, encrypted at rest.

    Exempt from tenant scoping: reached only as `tenant.secrets`, and read by
    platform code that already knows which tenant it is acting for.

    Nothing here is ever returned to a browser. The portal shows a masked
    value and can only overwrite it -- a compromised owner login must not be
    able to walk away with keys that move the client's money.
    """

    tenant_scoping_exempt = "one-to-one with Tenant; server-side reads only"

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="secrets")

    # WhatsApp
    wa_provider = models.CharField(
        max_length=20, choices=MessageProvider.choices, default=MessageProvider.CONSOLE
    )
    wa_phone_number_id = models.CharField(max_length=40, blank=True)
    wa_waba_id = models.CharField(max_length=40, blank=True)
    wa_verify_token = models.CharField(max_length=80, blank=True)
    _wa_token = models.TextField(blank=True, db_column="wa_token_enc")
    _wa_app_secret = models.TextField(blank=True, db_column="wa_app_secret_enc")

    # Where to POST when wa_provider is 'n8n'
    n8n_send_url = models.URLField(blank=True)
    _n8n_auth_token = models.TextField(blank=True, db_column="n8n_auth_token_enc")

    # Razorpay
    razorpay_key_id = models.CharField(max_length=60, blank=True)
    _razorpay_secret = models.TextField(blank=True, db_column="razorpay_secret_enc")
    _razorpay_webhook_secret = models.TextField(blank=True, db_column="rzp_webhook_secret_enc")
    razorpay_live_mode = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "tenant secrets"

    def __str__(self):
        return f"Secrets for {self.tenant.name}"

    # Encrypted fields are read and written through properties so callers
    # never see the ciphertext and never forget to encrypt.
    def _get(self, field):
        from .crypto import decrypt

        return decrypt(getattr(self, field))

    def _set(self, field, value):
        from .crypto import encrypt

        setattr(self, field, encrypt(value or ""))

    wa_token = property(lambda s: s._get("_wa_token"),
                        lambda s, v: s._set("_wa_token", v))
    wa_app_secret = property(lambda s: s._get("_wa_app_secret"),
                             lambda s, v: s._set("_wa_app_secret", v))
    n8n_auth_token = property(lambda s: s._get("_n8n_auth_token"),
                              lambda s, v: s._set("_n8n_auth_token", v))
    razorpay_secret = property(lambda s: s._get("_razorpay_secret"),
                               lambda s, v: s._set("_razorpay_secret", v))
    razorpay_webhook_secret = property(lambda s: s._get("_razorpay_webhook_secret"),
                                       lambda s, v: s._set("_razorpay_webhook_secret", v))

    @property
    def whatsapp_is_configured(self) -> bool:
        if self.wa_provider == MessageProvider.CONSOLE:
            return True
        if self.wa_provider == MessageProvider.N8N:
            return bool(self.n8n_send_url)
        return bool(self.wa_phone_number_id and self._wa_token)

    @property
    def razorpay_is_configured(self) -> bool:
        return bool(self.razorpay_key_id and self._razorpay_secret)
