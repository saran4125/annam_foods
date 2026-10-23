"""Imported images remain available even when the upload disk is empty."""
from io import BytesIO

import pytest
from PIL import Image
from django.http import Http404
from django.test import RequestFactory

from apps.content.media import public_media
from apps.tenancy.models import Tenant, TenantDomain

HEALTH_MIX = "menu/9c83d9e7554c03d281561c7a.jpg"
HOST = "media-preview.localhost"


@pytest.fixture
def media_kitchen(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.SERVE_MEDIA = True
    kitchen = Tenant.objects.create(slug="media-preview", name="Media preview")
    TenantDomain.objects.create(tenant=kitchen, hostname=HOST, is_primary=True)
    return tmp_path


@pytest.mark.parametrize("debug", [True, False])
def test_bundled_health_mix_is_a_real_image_when_the_upload_disk_is_empty(
    client, media_kitchen, settings, debug,
):
    settings.DEBUG = debug
    response = client.get("/media/" + HEALTH_MIX, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    content = b"".join(response.streaming_content)
    with Image.open(BytesIO(content)) as image:
        assert image.format == "JPEG"
        assert image.width >= 700 and image.height >= 700
        image.verify()
    assert (media_kitchen / HEALTH_MIX).read_bytes() == content


def test_owner_upload_takes_precedence_over_the_bundled_replacement(client, media_kitchen):
    upload = media_kitchen / HEALTH_MIX
    upload.parent.mkdir(parents=True)
    content = b"an owner uploaded replacement"
    upload.write_bytes(content)
    response = client.get("/media/" + HEALTH_MIX, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == content


def test_unknown_missing_media_still_returns_not_found(client, media_kitchen):
    response = client.get("/media/menu/unknown.jpg", HTTP_HOST=HOST)
    assert response.status_code == 404


def test_recovery_does_not_serve_bundled_directories(client, media_kitchen):
    response = client.get('/media/brand/', HTTP_HOST=HOST)
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["../branding/seer-logo.png", "/branding/seer-logo.png", "..\\branding\\seer-logo.png"])
def test_recovery_cannot_read_files_outside_the_public_media_namespace(path, settings):
    settings.SERVE_MEDIA = True
    request = RequestFactory().get("/media/unused")
    with pytest.raises(Http404):
        public_media(request, path)


def test_external_storage_mode_does_not_expose_local_or_bundled_files(client, media_kitchen, settings):
    settings.DEBUG = False
    settings.SERVE_MEDIA = False
    response = client.get("/media/" + HEALTH_MIX, HTTP_HOST=HOST)
    assert response.status_code == 404
