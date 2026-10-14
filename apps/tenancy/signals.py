from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BillingProfile, Tenant, TenantConfig


@receiver(post_save, sender=Tenant)
def create_default_tenant_config(sender, instance, created, **kwargs):
    if created:
        TenantConfig.objects.get_or_create(tenant=instance)
        BillingProfile.objects.get_or_create(
            tenant=instance, defaults={"legal_name": instance.name}
        )
