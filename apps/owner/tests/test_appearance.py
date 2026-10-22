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
