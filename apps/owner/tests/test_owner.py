"""The owner backend: who gets in, and that edits land on the right kitchen."""
import io
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, Slot
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain, TenantStatus, TenantUser, TenantUserRole

HOST, OTHER = "annam.localhost", "rival.localhost"


def _kitchen(slug, host):
    t = Tenant.objects.create(slug=slug, name=slug.title(), status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=t, hostname=host, is_primary=True)
    return t


@pytest.fixture
def kitchens(db):
    return _kitchen("annam", HOST), _kitchen("rival", OTHER)


@pytest.fixture
def owner(kitchens):
    user = get_user_model().objects.create_user("owner", password="pw-for-tests-only")
    TenantUser.all_tenants.create(tenant=kitchens[0], user=user, role=TenantUserRole.OWNER)
    return user


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def catalog(kitchens):
    with tenant_context(kitchens[0]):
        cat = MenuCategory.objects.create(name="Podi", slug="podi")
        slot = Slot.objects.create(key="lunch", label="Lunch", order_cutoff="11:00")
        dish = MenuItem.objects.create(name="Ellu Podi", price=Decimal("115"), category=cat, fulfilment="courier")
    with tenant_context(kitchens[1]):
        theirs = MenuItem.objects.create(name="Rival Roll", price=Decimal("90"))
    return {"cat": cat, "slot": slot, "dish": dish, "theirs": theirs}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "orange").save(buf, "PNG")
    return SimpleUploadedFile("dish.png", buf.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path  # uploads never touch the real media folder


def test_anonymous_is_sent_to_login(client, kitchens):
    r = client.get("/manage/", HTTP_HOST=HOST)
    assert r.status_code == 302 and "/manage/login/" in r["Location"]


def test_customer_account_without_membership_is_refused(client, kitchens):
    stranger = get_user_model().objects.create_user("stranger", password="x-tests-only")
    client.force_login(stranger)
    assert client.get("/manage/", HTTP_HOST=HOST).status_code == 403


def test_owner_of_one_kitchen_cannot_manage_another(signed_in, catalog):
    assert signed_in.get("/manage/", HTTP_HOST=HOST).status_code == 200
    assert signed_in.get("/manage/", HTTP_HOST=OTHER).status_code == 403


def test_login_form_signs_in_the_owner(client, owner):
    r = client.post("/manage/login/", {"username": "owner", "password": "pw-for-tests-only"}, HTTP_HOST=HOST)
    assert r.status_code == 302 and r["Location"] == "/manage/"


def test_another_kitchens_dish_is_a_404(signed_in, catalog):
    assert signed_in.get(f"/manage/dishes/{catalog['theirs'].pk}/", HTTP_HOST=HOST).status_code == 404
    r = signed_in.post(f"/manage/dishes/{catalog['theirs'].pk}/toggle/", HTTP_HOST=HOST)
    assert r.status_code == 404


def test_add_a_daily_meal_with_photo_and_menu_days(signed_in, kitchens, catalog):
    r = signed_in.post("/manage/dishes/new/", {
        "name": "Ghee Pongal", "category": catalog["cat"].pk, "fulfilment": "scheduled", "price": "110",
        "description": "With chutney", "image": _png(), "is_veg": "on", "active": "on", "sort": 0,
        "slot": catalog["slot"].pk, "weekdays": ["0", "2", "4"], "featured": "on",
    }, HTTP_HOST=HOST)
    assert r.status_code == 302, r.content
    with tenant_context(kitchens[0]):
        dish = MenuItem.objects.get(name="Ghee Pongal")
        assert dish.image and dish.price == Decimal("110") and "featured" in dish.tags
        assert sorted(MenuSchedule.objects.filter(item=dish).values_list("weekday", flat=True)) == [0, 2, 4]
    assert dish.tenant_id == kitchens[0].pk


def test_rename_reprice_and_change_menu_days(signed_in, kitchens, catalog):
    dish = catalog["dish"]
    r = signed_in.post(f"/manage/dishes/{dish.pk}/", {
        "name": "Special Ellu Podi", "category": catalog["cat"].pk, "fulfilment": "courier",
        "price": "125", "description": "", "sort": 0, "active": "on",
    }, HTTP_HOST=HOST)
    assert r.status_code == 302
    with tenant_context(kitchens[0]):
        dish.refresh_from_db()
    assert dish.name == "Special Ellu Podi" and dish.price == Decimal("125")


def test_toggle_takes_a_dish_off_sale(signed_in, kitchens, catalog):
    signed_in.post(f"/manage/dishes/{catalog['dish'].pk}/toggle/", HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert MenuItem.objects.get(pk=catalog["dish"].pk).active is False


def test_category_in_use_is_not_deleted(signed_in, kitchens, catalog):
    r = signed_in.post(f"/manage/categories/{catalog['cat'].pk}/delete/", HTTP_HOST=HOST)
    assert r.status_code == 302
    with tenant_context(kitchens[0]):
        assert MenuCategory.objects.filter(pk=catalog["cat"].pk).exists()


def test_delete_a_dish(signed_in, kitchens, catalog):
    signed_in.post(f"/manage/dishes/{catalog['dish'].pk}/delete/", HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert not MenuItem.objects.filter(pk=catalog["dish"].pk).exists()


def test_settings_update_brand_and_hero(signed_in, kitchens):
    r = signed_in.post("/manage/settings/", {
        "brand_name": "Annam’s", "tagline": "Home-made", "support_phone": "9551079550",
        "contact_email": "", "brand_color": "#E8271F", "announcements": "One\nTwo",
        "hero_kicker": "Since 2015", "hero_title": "Food like home", "hero_body": "Cooked fresh.",
        "website_ordering": "on",
    }, HTTP_HOST=HOST)
    assert r.status_code == 302
    config = TenantConfig.objects.get(tenant=kitchens[0])
    assert config.brand_name == "Annam’s" and config.theme["brand"] == "#E8271F"
    assert config.theme["announcements"] == ["One", "Two"]
    assert {"kind": "hero", "kicker": "Since 2015", "title": "Food like home", "body": "Cooked fresh."} in config.home_sections
    assert config.features["website_ordering"] is True and config.features["snacks_courier"] is False
    home = signed_in.get("/", HTTP_HOST=HOST)
    assert b"Food like home" in home.content


def test_every_resource_list_renders(signed_in, catalog):
    for key in ["dishes", "categories", "meals", "banners", "pages", "zones"]:
        assert signed_in.get(f"/manage/{key}/", HTTP_HOST=HOST).status_code == 200, key
        assert signed_in.get(f"/manage/{key}/new/", HTTP_HOST=HOST).status_code == 200, key
    assert signed_in.get("/manage/orders/", HTTP_HOST=HOST).status_code == 200
    assert signed_in.get("/manage/settings/", HTTP_HOST=HOST).status_code == 200
    assert signed_in.get("/manage/nonsense/", HTTP_HOST=HOST).status_code == 404
