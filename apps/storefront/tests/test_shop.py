"""The shop: courier goods browsed by shelf, and the cart that carries them.

Shop items and scheduled meals are priced and delivered differently, so a cart
holds one kind or the other -- never both. These tests pin that rule, the
snacks_courier flag in both states, and server-side pricing for shop lines.
"""
from decimal import Decimal

import pytest

from apps.catalog.models import MenuCategory, MenuItem
from apps.delivery.models import DeliveryZone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig

from .test_storefront import HOST, _add, kitchen, menu  # noqa: F401 (fixtures)


@pytest.fixture
def shop(kitchen):  # noqa: F811
    TenantConfig.objects.filter(tenant=kitchen).update(features={"snacks_courier": True})
    kitchen.refresh_from_db()
    with tenant_context(kitchen):
        snacks = MenuCategory.objects.create(name="Pakshanams", slug="pakshanams", sort=1)
        murukku = MenuCategory.objects.create(name="Murukku", slug="murukku", parent=snacks)
        podi = MenuCategory.objects.create(name="Podi", slug="podi", sort=0)
        butter = MenuItem.objects.create(name="Butter Murukku", price=Decimal("140"),
                                         category=murukku, fulfilment="courier")
        ellu = MenuItem.objects.create(name="Ellu Podi", price=Decimal("115"),
                                       category=podi, fulfilment="courier", tags=["featured"])
        hidden = MenuItem.objects.create(name="Kaju Kathli", price=Decimal("350"),
                                         category=snacks, fulfilment="courier", active=False)
        DeliveryZone.objects.get_or_create(
            pincode="600005", area_name="Triplicane",
            defaults={"delivery_fee": Decimal("30"), "min_order": Decimal("200")},
        )
    return {"butter": butter, "ellu": ellu, "hidden": hidden, "snacks": snacks}


def _shop_add(client, item, delta=1):
    return client.post("/cart/add/", {"kind": "shop", "item_id": item.id, "delta": delta}, HTTP_HOST=HOST)


def test_shop_is_off_unless_the_kitchen_sells_courier_goods(client, kitchen):  # noqa: F811
    assert client.get("/shop/", HTTP_HOST=HOST).status_code == 404
    r = client.post("/cart/add/", {"kind": "shop", "item_id": 1, "delta": 1}, HTTP_HOST=HOST)
    assert r.status_code == 404


def test_shop_lists_only_active_courier_goods(client, shop):
    r = client.get("/shop/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Butter Murukku" in r.content and b"Ellu Podi" in r.content
    assert b"Kaju Kathli" not in r.content


def test_parent_shelf_includes_its_children(client, shop):
    r = client.get("/shop/pakshanams/", HTTP_HOST=HOST)
    assert b"Butter Murukku" in r.content
    assert b"Ellu Podi" not in r.content


def test_search_and_unknown_shelf(client, shop):
    r = client.get("/shop/?q=podi", HTTP_HOST=HOST)
    assert b"Ellu Podi" in r.content and b"Butter Murukku" not in r.content
    assert client.get("/shop/nope/", HTTP_HOST=HOST).status_code == 404
    assert client.get("/shop/?sort=evil", HTTP_HOST=HOST).status_code == 200


def test_inactive_item_has_no_page(client, shop):
    assert client.get(f"/item/{shop['ellu'].id}/", HTTP_HOST=HOST).status_code == 200
    assert client.get(f"/item/{shop['hidden'].id}/", HTTP_HOST=HOST).status_code == 404


def test_shop_cart_prices_from_the_catalog_and_checks_delivery(client, shop):
    _shop_add(client, shop["butter"])
    _shop_add(client, shop["butter"])
    client.post("/cart/pincode/", {"pincode": "600005"}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Butter Murukku" in r.content
    assert b"310" in r.content          # 2 x 140 + 30 delivery
    assert b'data-blocked' not in r.content


def test_inactive_shop_item_cannot_be_added(client, shop):
    _shop_add(client, shop["hidden"])
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


def test_meals_and_shop_items_never_share_a_cart(client, shop, menu):  # noqa: F811
    _shop_add(client, shop["ellu"])
    _add(client, menu)
    page = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Ellu Podi" in page.content and b"Veg Meals" not in page.content

    client.post("/cart/clear/", HTTP_HOST=HOST)
    _add(client, menu)
    _shop_add(client, shop["ellu"])
    page = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in page.content and b"Ellu Podi" not in page.content


def test_home_shows_shelves_and_featured_goods(client, shop):
    r = client.get("/", HTTP_HOST=HOST)
    assert b"Pakshanams" in r.content
    assert b"Ellu Podi" in r.content
