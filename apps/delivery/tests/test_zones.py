from decimal import Decimal

import pytest

from apps.delivery.models import DeliveryZone
from apps.delivery.services import normalise_pincode, zones_for_pincode
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="annam", name="Annam Foods", status="active")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600106", "600106"),
        ("600 106", "600106"),      # the bug Annam's bot actually hit
        ("600-106", "600106"),
        (" 600106 ", "600106"),
        ("pincode 600106", "600106"),
        ("", ""),
        (None, ""),
    ],
)
def test_pincode_normalisation(raw, expected):
    assert normalise_pincode(raw) == expected


def test_serviceable_pincode_returns_its_zone(kitchen):
    with tenant_context(kitchen):
        DeliveryZone.objects.create(
            pincode="600106", area_name="Ashok Nagar",
            delivery_fee=Decimal("30"), min_order=Decimal("200"),
        )
        zones = zones_for_pincode("600 106")
        assert len(zones) == 1
        assert zones[0].area_name == "Ashok Nagar"


def test_unknown_pincode_returns_nothing(kitchen):
    with tenant_context(kitchen):
        assert zones_for_pincode("110001") == []


def test_malformed_pincode_returns_nothing(kitchen):
    with tenant_context(kitchen):
        assert zones_for_pincode("60010") == []
        assert zones_for_pincode("abcdef") == []


def test_one_pincode_can_hold_several_areas(kitchen):
    with tenant_context(kitchen):
        DeliveryZone.objects.create(pincode="641001", area_name="RS Puram", delivery_fee=20)
        DeliveryZone.objects.create(pincode="641001", area_name="Gandhipuram", delivery_fee=40)
        assert len(zones_for_pincode("641001")) == 2


def test_zone_can_be_limited_to_certain_slots(kitchen):
    with tenant_context(kitchen):
        DeliveryZone.objects.create(
            pincode="641002", area_name="Far Side", slot_keys=["lunch"]
        )
        assert len(zones_for_pincode("641002", slot_key="lunch")) == 1
        assert zones_for_pincode("641002", slot_key="dinner") == []


def test_empty_slot_list_means_every_slot(kitchen):
    with tenant_context(kitchen):
        DeliveryZone.objects.create(pincode="641003", area_name="Central", slot_keys=[])
        assert len(zones_for_pincode("641003", slot_key="dinner")) == 1


def test_zones_do_not_leak_between_kitchens(kitchen, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status="active")
    with tenant_context(kitchen):
        DeliveryZone.objects.create(pincode="600106", area_name="Ashok Nagar")
    with tenant_context(rival):
        assert zones_for_pincode("600106") == []
