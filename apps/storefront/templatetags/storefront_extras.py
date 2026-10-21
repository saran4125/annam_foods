from django import template
from django.utils.safestring import mark_safe

from apps.content.services import safe_link as _safe_link

register = template.Library()


@register.filter
def dictkey(mapping, key):
    """Look up a dict by a variable key.

    Django templates can't do `d[k]`. Cart quantities are keyed by item id as
    a string, so try both forms rather than making the view reshape the data.
    """
    if not mapping:
        return None
    return mapping.get(key, mapping.get(str(key)))


@register.filter
def money(value):
    """A price as a customer should see it — paise preserved (FIX-14).

    120 stays 120; 120.50 stays 120.50. Zero-decimal formatting that rounds a
    real amount down to the rupee is how a kitchen ends up billing 120 for a
    120.50 dish.
    """
    from decimal import Decimal, InvalidOperation

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        return value
    text = f"{amount:.2f}"
    return text[:-3] if text.endswith(".00") else text


@register.filter
def safe_link(value):
    """Only render a followable link (FIX-09).

    Banner destinations are kitchen-written content; an unsafe destination
    renders as nothing rather than a hostile `href`.
    """
    if _safe_link(value):
        return value
    return mark_safe("")


@register.filter
def tile_tint(value):
    """A stable tint index (0-5) for a dish with no photograph.

    Deterministic on the name, so a dish keeps the same colour on every page
    and across restarts -- a menu that reshuffles its colours on refresh looks
    broken rather than lively.
    """
    return sum(ord(c) for c in str(value or "")) % 6


@register.filter
def words(value):
    """Split a headline into words, so each can be revealed in turn."""
    return str(value or "").split()


@register.simple_tag
def static_v(path):
    """A static URL with the file's modification time, so a browser never keeps
    serving yesterday's stylesheet after a change."""
    import os

    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    url = static(path)
    found = finders.find(path)
    if found and not isinstance(found, (list, tuple)):
        url += f"?v={int(os.path.getmtime(found))}"
    return url


@register.filter
def workspace_link(value, request):
    """Keep root-relative owner content links inside a private website preview."""
    prefix = getattr(request, "workspace_preview_url", "")
    if prefix and isinstance(value, str) and value.startswith("/") and not value.startswith(("//", "/platform/", "/static/", "/media/")):
        return prefix.rstrip("/") + value
    return value


@register.filter
def root_media_url(value):
    """Old JSON sections saved storage URLs as ``media/...`` before the
    production storage fix. Resolve those at the site root even in a private
    preview; leave absolute media and external image URLs unchanged.
    """
    if isinstance(value, str) and value.startswith("media/"):
        return "/" + value
    return value
