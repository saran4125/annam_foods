"""Create a kitchen. This is the whole of onboarding, and it should stay that way.

    ./manage.py provision_tenant --slug annam --name "Annam Foods" \
        --domain annam.localhost --owner-email owner@example.com
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from apps.tenancy.models import (
    Tenant,
    TenantConfig,
    TenantDomain,
    TenantStatus,
    TenantUser,
    TenantUserRole,
)


class Command(BaseCommand):
    help = "Provision a new cloud kitchen tenant."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--domain", required=True)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--menu-mode", default="daily", choices=["daily", "weekly"])
        parser.add_argument("--phone", default="")

    @transaction.atomic
    def handle(self, *args, **opts):
        slug = opts["slug"]
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"A tenant with slug '{slug}' already exists.")

        tenant = Tenant.objects.create(
            slug=slug,
            name=opts["name"],
            primary_domain=opts["domain"].lower(),
            status=TenantStatus.ACTIVE,
        )
        TenantDomain.objects.create(
            tenant=tenant, hostname=opts["domain"], is_primary=True
        )
        TenantConfig.objects.create(
            tenant=tenant,
            brand_name=opts["name"],
            menu_mode=opts["menu_mode"],
            support_phone=opts["phone"],
        )

        email = opts["owner_email"]
        user, created = User.objects.get_or_create(
            username=email, defaults={"email": email}
        )
        password = None
        if created:
            password = get_random_string(12)
            user.set_password(password)
            user.save()

        TenantUser.all_tenants.create(
            tenant=tenant, user=user, role=TenantUserRole.OWNER
        )

        self.stdout.write(self.style.SUCCESS(f"Provisioned {tenant.name}"))
        self.stdout.write(f"  slug     {tenant.slug}")
        self.stdout.write(f"  hostname {opts['domain']}")
        self.stdout.write(f"  owner    {email}")
        if password:
            self.stdout.write(
                self.style.WARNING(f"  password {password}  (shown once)")
            )
