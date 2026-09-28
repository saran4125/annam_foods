"""Exercise the real add path and report the outcome code."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.delivery.models import DeliveryZone
from apps.storefront import services
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain, TenantStatus

HOST = "annam.localhost"


def test_diagnose(client, db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=t, hostname=HOST, is_primary=True)
    TenantConfig.objects.create(tenant=t, brand_name="Annam Foods")
    today = timezone.localdate()
    late = (timezone.localtime() + timedelta(hours=3)).time()
    with tenant_context(t):
        slot = Slot.objects.create(key="lunch", label="Lunch", order_cutoff=late, sort=1)
        item = MenuItem.objects.create(name="Veg Meals", price=Decimal("120"))
        MenuSchedule.objects.create(item=item, slot=slot, mode=ScheduleMode.DATE, on_date=today)
        DeliveryZone.objects.create(pincode="641001", area_name="RS Puram",
                                    delivery_fee=Decimal("20"), min_order=Decimal("150"))

    r = client.post("/cart/add/", {
        "item_id": item.id, "delta": 1,
        "slot_key": slot.key, "delivery_date": today.isoformat(),
    }, HTTP_HOST=HOST, follow=True)

    msgs = [str(m) for m in r.context["messages"]] if r.context and "messages" in r.context else []
    print("\n--- redirect chain:", r.redirect_chain)
    print("--- messages:", msgs)
    print("--- session keys:", list(client.session.keys()))
    for k in client.session.keys():
        print(f"      {k} = {client.session[k]}")
    print("--- 'Veg Meals' on page:", b"Veg Meals" in r.content)
