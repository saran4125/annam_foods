"""Visual copy/photo edits are drafts until published, with tenant-safe uploads."""
import io
from copy import deepcopy

import pytest
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.content.models import StorefrontImage
from apps.content.services import default_storefront_design, validate_storefront_design
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig, TenantUser
from .test_appearance import kitchens, owner, payload, HOST, OTHER


def photo(name='kitchen.png'):
    out = io.BytesIO()
    Image.new('RGB', (24, 24), '#eeaa55').save(out, format='PNG')
    return SimpleUploadedFile(name, out.getvalue(), content_type='image/png')


def test_unknown_content_fields_and_overlong_copy_cannot_enter_a_design(kitchens):
    design = default_storefront_design(kitchens[0].config)
    design['content'] = {'checkout.total': '1'}
    with pytest.raises(ValidationError):
        validate_storefront_design(design)
    design['content'] = {'hero.title': 'x' * 161}
    with pytest.raises(ValidationError):
        validate_storefront_design(design)


def test_closing_keeps_original_menu_photos_and_offers_empty_editor_slots():
    from types import SimpleNamespace
    from django.template import Context
    from apps.storefront.templatetags.storefront_extras import closing_photos

    picks = [SimpleNamespace(image=SimpleNamespace(url=f'/media/{i}.jpg')) for i in range(3)]
    assert [slot['url'] for slot in closing_photos(Context({'hero_picks': picks}))] == [p.image.url for p in picks]
    slots = closing_photos(Context({'hero_picks': picks, 'storefront_images': {'closing_2': '/replacement/'}}))
    assert [slot['url'] for slot in slots] == ['/media/0.jpg', '/replacement/', '/media/2.jpg']
    assert closing_photos(Context({'hero_picks': picks[:1]})) == []
    empty = closing_photos(Context({'appearance_canvas': True}))
    assert [slot['key'] for slot in empty] == ['closing_1', 'closing_2', 'closing_3']
    assert all(not slot['url'] for slot in empty)
