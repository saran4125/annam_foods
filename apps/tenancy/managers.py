"""Tenant scoping.

The rule this file enforces: a query against tenant-owned data either carries a
tenant, or it raises. Writing an unscoped query has to be a deliberate act
(`all_tenants()`), never an accident of forgetting `.filter(tenant=...)`.
"""
from django.db import models

from .context import TenantContextMissing, get_current_tenant, is_unscoped


class TenantScopedQuerySet(models.QuerySet):
    pass


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):
    """Default manager for tenant-owned models. Filters to the current tenant."""

    def get_queryset(self):
        qs = super().get_queryset()
        if is_unscoped():
            return qs
        tenant = get_current_tenant()
        if tenant is None:
            raise TenantContextMissing(
                f"{self.model.__name__} was queried with no tenant in context. "
                f"Wrap the call in tenant_context(tenant) for a single kitchen, "
                f"or all_tenants() if you genuinely mean every kitchen."
            )
        return qs.filter(tenant=tenant)


class TenantOwnedModel(models.Model):
    """Base class for anything that belongs to one kitchen.

    Gives you:
      objects      - scoped to the current tenant, raises without one
      all_tenants  - unscoped, for platform-level code only

    `base_manager_name` points at the unscoped manager on purpose: Django uses
    the base manager to follow foreign keys, and that must keep working even
    when no tenant context is set (inside the admin, for instance).
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    objects = TenantScopedManager()
    all_tenants = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args, **kwargs):
        # Stamp the tenant automatically so callers can't forget it.
        if self.tenant_id is None:
            current = get_current_tenant()
            if current is None:
                raise TenantContextMissing(
                    f"Tried to save a {type(self).__name__} with no tenant set."
                )
            self.tenant = current
        return super().save(*args, **kwargs)
