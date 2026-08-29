"""Give a tenant a realistic menu to develop the storefront against.

    ./manage.py seed_demo_menu --tenant annam
"""
from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.delivery.models import DeliveryZone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

SLOTS = [
    ("breakfast", "Breakfast", time(9, 0), time(7, 30), time(9, 30), 1),
    ("lunch", "Lunch", time(11, 0), time(12, 30), time(14, 0), 2),
    ("dinner", "Dinner", time(19, 0), time(19, 30), time(21, 30), 3),
]

MENU = {
    "breakfast": [("Idly (4)", "Steamed rice cakes with chutney and sambar", "40", True),
                  ("Pongal", "Ghee pongal with vada", "60", True),
                  ("Masala Dosa", "Crisp dosa with potato masala", "70", True)],
    "lunch": [("Veg Meals", "Rice, sambar, rasam, two poriyal, curd, appalam", "120", True),
              ("Chicken Biryani", "Seeraga samba rice, bone-in chicken", "180", False),
              ("Curd Rice", "With pickle", "60", True)],
    "dinner": [("Chapati (3)", "With kurma", "70", True),
               ("Parotta (2)", "With salna", "80", True),
               ("Egg Fried Rice", "", "110", False)],
}

ZONES = [
    ("641001", "RS Puram", "20", "150"),
    ("641002", "Gandhipuram", "30", "150"),
    ("641038", "Peelamedu", "40", "200"),
]


class Command(BaseCommand):
    help = "Seed a demo menu, slots and delivery zones for one tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="tenant slug")

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant with slug '{opts['tenant']}'.")

        with tenant_context(tenant):
            slots = {}
            for key, label, cutoff, d_from, d_to, sort in SLOTS:
                slot, _ = Slot.objects.get_or_create(
                    key=key,
                    defaults=dict(
                        label=label, order_cutoff=cutoff,
                        delivery_from=d_from, delivery_to=d_to, sort=sort,
                    ),
                )
                slots[key] = slot

            category, _ = MenuCategory.objects.get_or_create(name="Today's Menu")

            created = 0
            for slot_key, dishes in MENU.items():
                for sort, (name, desc, price, veg) in enumerate(dishes):
                    item, _ = MenuItem.objects.get_or_create(
                        name=name,
                        defaults=dict(
                            description=desc, price=Decimal(price),
                            is_veg=veg, category=category, sort=sort,
                        ),
                    )
                    # A standing weekly template, Monday to Saturday.
                    # Sunday is deliberately left off — Annam doesn't serve it.
                    for weekday in range(0, 6):
                        _, made = MenuSchedule.objects.get_or_create(
                            item=item, slot=slots[slot_key],
                            mode=ScheduleMode.WEEKDAY, weekday=weekday,
                        )
                        created += int(made)

            for pincode, area, fee, minimum in ZONES:
                DeliveryZone.objects.get_or_create(
                    pincode=pincode, area_name=area,
                    defaults=dict(delivery_fee=Decimal(fee), min_order=Decimal(minimum)),
                )

        self.stdout.write(self.style.SUCCESS(f"Seeded {tenant.name}"))
        self.stdout.write(f"  slots      {len(SLOTS)}")
        self.stdout.write(f"  items      {sum(len(v) for v in MENU.values())}")
        self.stdout.write(f"  schedule   {created} weekly rows (Mon-Sat, no Sunday)")
        self.stdout.write(f"  zones      {len(ZONES)}")
