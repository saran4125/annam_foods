"""Kitchen appearance is published deliberately and drafts never cross tenants."""
from copy import deepcopy

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.content.services import change_storefront_design, default_storefront_design, validate_storefront_design
from apps.storefront.themes import SECTIONS
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain, TenantStatus, TenantUser

HOST, OTHER = "appearance.localhost", "other-appearance.localhost"


@pytest.fixture
def kitchens(db):
    result = []
    for slug, host in (("appearance", HOST), ("other-appearance", OTHER)):
        tenant = Tenant.objects.create(slug=slug, name=slug, status=TenantStatus.ACTIVE)
        TenantDomain.objects.create(tenant=tenant, hostname=host, is_primary=True)
        result.append(tenant)
    return result


@pytest.fixture
def owner(kitchens):
    user = get_user_model().objects.create_user(username="appearance-owner")
    TenantUser.all_tenants.create(tenant=kitchens[0], user=user, role="owner")
    return user


def payload(config, action="save", revision=0):
    design = default_storefront_design(config)
    data = {key: design[key] for key in ("font", "density", "shape", "hero_layout", "menu_layout")}
    data.update(design["colors"], action=action, revision=revision)
    data.update({f"order_{key}": i for i, (key, _, _) in enumerate(SECTIONS, 1)})
    data.update({f"show_{key}": "on" for key, _, _ in SECTIONS})
    return data


def test_existing_kitchen_keeps_its_brand_and_default_section_order(client, kitchens):
    config = kitchens[0].config
    config.theme = {"brand": "#228844", "font_display": "Georgia,serif"}
    config.save()
    response = client.get("/", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert response.context["storefront_theme"] == config.theme
    assert [s["key"] for s in response.context["storefront_sections"]] == [key for key, _, _ in SECTIONS]
    config.refresh_from_db()
    assert config.storefront_design == {}


def test_saved_draft_is_private_and_does_not_change_the_public_storefront(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data.update(brand="#336699", hero_layout="centered")
    data.pop("show_story")
    assert client.post("/manage/appearance/", data, HTTP_HOST=HOST).status_code == 302
    public = client.get("/", HTTP_HOST=HOST)
    assert public.context["storefront_design"]["hero_layout"] == "split"
    assert b'data-home-section="story"' in public.content
    preview = client.get("/?design=draft", HTTP_HOST=HOST)
    assert preview.status_code == 200
    assert preview.context["storefront_theme"]["brand"] == "#336699"
    assert b'data-home-section="story"' not in preview.content
    assert b"sf-hero-centered" in preview.content
    assert "private" in preview["Cache-Control"] and "no-store" in preview["Cache-Control"]
    assert preview["X-Robots-Tag"] == "noindex, nofollow"
    assert client.get("/?design=draft", HTTP_HOST=OTHER).status_code == 403
    client.logout()
    assert client.get("/?design=draft", HTTP_HOST=HOST).status_code == 403


def test_publish_reorders_sections_and_only_changes_the_selected_kitchen(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config, action="publish")
    data.update(order_hero=3, order_meals=1, brand="#336699", font="clean", menu_layout="list")
    assert client.post("/manage/appearance/", data, HTTP_HOST=HOST).status_code == 302
    client.logout()
    public = client.get("/", HTTP_HOST=HOST)
    text = public.content.decode()
    assert text.index('data-home-section="meals"') < text.index('data-home-section="hero"')
    assert public.context["storefront_theme"]["brand"] == "#336699"
    assert public.context["storefront_design"]["menu_layout"] == "list"
    assert client.get("/menu/", HTTP_HOST=HOST).context["storefront_theme"]["brand"] == "#336699"
    other = client.get("/", HTTP_HOST=OTHER)
    assert other.context["storefront_design"]["menu_layout"] == "columns"
    assert other.context["storefront_theme"].get("brand") != "#336699"
    assert not TenantConfig.objects.get(tenant=kitchens[1]).storefront_design


def test_restore_returns_to_the_previous_published_design_and_discard_removes_only_the_draft(kitchens):
    tenant = kitchens[0]
    original = default_storefront_design(tenant.config)
    draft = deepcopy(original)
    draft["hero_layout"] = "centered"
    change_storefront_design(tenant, action="publish", revision=0, design=draft)
    change_storefront_design(tenant, action="save", revision=1, design=original)
    state = change_storefront_design(tenant, action="discard", revision=2)
    assert "draft" not in state and state["published"]["hero_layout"] == "centered"
    state = change_storefront_design(tenant, action="restore", revision=3)
    assert state["published"] == original
    assert state["previous"]["hero_layout"] == "centered"


def test_an_old_editor_cannot_overwrite_a_newer_draft(kitchens):
    tenant = kitchens[0]
    design = default_storefront_design(tenant.config)
    change_storefront_design(tenant, action="save", revision=0, design=design)
    design["font"] = "clean"
    with pytest.raises(ValidationError, match="another session"):
        change_storefront_design(tenant, action="publish", revision=0, design=design)
    state = TenantConfig.objects.get(tenant=tenant).storefront_design
    assert state["draft"]["font"] == "inherit" and "published" not in state


@pytest.mark.parametrize("change", ["template", "injection", "duplicates", "empty", "contrast", "dark-background"])
def test_unsafe_or_unreadable_design_choices_are_rejected(kitchens, change):
    design = default_storefront_design(kitchens[0].config)
    if change == "template":
        design["theme"] = "../../secrets"
    elif change == "injection":
        design["colors"]["brand"] = "red;}body{display:none}"
    elif change == "duplicates":
        design["sections"][1] = design["sections"][0]
    elif change == "empty":
        for section in design["sections"]:
            section["enabled"] = False
    elif change == "contrast":
        design["colors"]["ink"] = design["colors"]["paper"]
    else:
        design["colors"].update(paper="#000000", ink="#FFFFFF")
    with pytest.raises(ValidationError):
        validate_storefront_design(design)


def test_owner_cannot_edit_another_kitchens_appearance(client, kitchens, owner):
    client.force_login(owner)
    response = client.post("/manage/appearance/", payload(kitchens[1].config, action="publish"), HTTP_HOST=OTHER)
    assert response.status_code == 403
    assert client.get("/platform/workspaces/other-appearance/manage/appearance/", HTTP_HOST=HOST).status_code == 404
    assert not TenantConfig.objects.get(tenant=kitchens[1]).storefront_design


def test_editor_requires_login_and_accepts_a_native_form_without_javascript(client, kitchens, owner):
    assert client.get("/manage/appearance/", HTTP_HOST=HOST).status_code == 302
    client.force_login(owner)
    response = client.get("/manage/appearance/", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert len(response.context["form"].section_rows) == len(SECTIONS)
    data = payload(kitchens[0].config)
    data.update(order_hero=2, order_offers=1)
    response = client.post("/manage/appearance/", data, HTTP_HOST=HOST)
    assert response.status_code == 302
    state = TenantConfig.objects.get(tenant=kitchens[0]).storefront_design
    assert state["draft"]["sections"][0]["key"] == "offers"


def test_invalid_positions_and_unknown_actions_do_not_save_changes(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data["order_offers"] = 1
    response = client.post("/manage/appearance/", data, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b"different position" in response.content
    response = client.post("/manage/appearance/", payload(kitchens[0].config, action="unknown"), HTTP_HOST=HOST)
    assert response.status_code == 200
    assert not TenantConfig.objects.get(tenant=kitchens[0]).storefront_design


def test_private_workspace_can_preview_its_saved_draft(client, kitchens, owner):
    client.force_login(owner)
    base = "/platform/workspaces/appearance/"
    data = payload(kitchens[0].config)
    data["shape"] = "square"
    assert client.post(base + "manage/appearance/", data, HTTP_HOST=HOST).status_code == 302
    preview = client.get(base + "preview/?design=draft", HTTP_HOST=HOST)
    assert preview.status_code == 200 and preview.context["appearance_preview"]
    assert b"sf-shape-square" in preview.content
    assert (base + "manage/appearance/").encode() in preview.content
    public_preview = client.get(base + "preview/", HTTP_HOST=HOST)
    assert public_preview.context["storefront_design"]["shape"] == "original"


def test_publishing_preserves_content_and_the_existing_brand_control_stays_effective(client, kitchens, owner):
    config = kitchens[0].config
    config.home_sections = [{"kind": "hero", "title": "Our original headline"}]
    config.theme = {"brand": "#FF8507", "logo_url": "/media/brand/logo.png", "contact_email": "owner@example.test"}
    config.save()
    design = default_storefront_design(config)
    design["colors"]["brand"] = "#336699"
    change_storefront_design(kitchens[0], action="publish", revision=0, design=design)
    config.refresh_from_db()
    assert config.home_sections == [{"kind": "hero", "title": "Our original headline"}]
    assert config.theme["logo_url"] == "/media/brand/logo.png"
    assert config.theme["contact_email"] == "owner@example.test"
    config.theme["brand"] = "#118844"
    config.save(update_fields=["theme"])
    client.force_login(owner)
    editor = client.get("/manage/appearance/", HTTP_HOST=HOST)
    assert editor.context["form"].initial["brand"] == "#118844"
    assert "no-store" in editor["Cache-Control"]
    assert client.get("/", HTTP_HOST=HOST).context["storefront_theme"]["brand"] == "#118844"


def test_publish_cannot_bypass_csrf_protection(kitchens, owner):
    from django.test import Client
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    response = client.post("/manage/appearance/", payload(kitchens[0].config, action="publish"), HTTP_HOST=HOST)
    assert response.status_code == 403
    assert not TenantConfig.objects.get(tenant=kitchens[0]).storefront_design
