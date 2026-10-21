"""Content resolution and trust boundaries.

The storefront must never inherit the shape of the raw Banner queryset. These
services decide what a campaign actually is -- a valid, in-window slide with an
image -- so the template can render a finished list instead of re-filtering a
raw slice (`FIX-01`, `FIX-02`). They are also the one place page and banner
content is sanitised before it reaches a browser (`FIX-09`).
"""
from html.parser import HTMLParser

_SAFE_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "em",
    "blockquote", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "img",
}

# Elements that must never render their content either -- script bodies and
# executable/form markup are dropped wholesale, not stripped of their tags.
_BLOCKED_TAGS = {
    "script", "style", "iframe", "object", "embed", "link", "meta", "form",
    "svg", "math", "template", "noscript", "input", "button", "textarea",
    "select", "option", "audio", "video", "source", "track",
}

_SAFE_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def safe_link(value: str | None) -> str | None:
    """Only links a customer can safely follow.

    Rejects JavaScript/data/script/foo schemes and protocol-relative URLs.
    Relative storefront paths (`/menu/`, `?slot=…`) are fine. Returns None for
    anything unsafe so a template renders a non-linked item rather than a dead
    or hostile `<a href>`.
    """
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    lower = candidate.lower()
    if lower.startswith("//") or lower.startswith("\\\\"):
        return None
    if "://" in candidate or ":" in candidate:
        scheme = candidate.split(":", 1)[0].lower()
        if scheme not in _SAFE_URL_SCHEMES:
            return None
    return candidate


def resolve_campaigns(limit: int = 3):
    """Active promotions with an image, deterministically ordered.

    Empty records (no image) never reach the template -- they must not be able
    to shift the slider's active state or dot indices."""
    from .models import Banner

    return list(
        Banner.objects.filter(active=True)
        .exclude(image="")
        .order_by("sort", "id")[:limit]
    )


def resolve_hero_slides(limit: int = 3):
    """The hero needs image-bearing slides, nothing else."""
    return resolve_campaigns(limit=limit)


def resolve_promo_tiles(limit: int = 3, exclude_hero=True):
    """The promotion rail is an independent placement.

    It never reuses the hero slides (that double-shows the same campaign) and
    only renders tiles that have somewhere to go -- a linked campaign. A
    missing destination disappears rather than becoming `href="#"`.
    """
    hero_ids = {s.id for s in resolve_hero_slides()} if exclude_hero else set()
    tiles = []
    for banner in resolve_campaigns(limit=limit * 4):
        if banner.id in hero_ids:
            continue
        if not safe_link(banner.link):
            continue
        tiles.append(banner)
        if len(tiles) >= limit:
            break
    return tiles


class _AllowlistParser(HTMLParser):
    """Drop every tag/attribute that isn't allowlisted and neutralise
    script/event-handler/bad-URL content. Markdown output is otherwise trusted
    by the template with `|safe`, so this is the trust boundary."""

    VOID = {"br", "hr", "img"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._stack = []  # tags we are inside; "block" marks a dropped element

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _BLOCKED_TAGS:
            self._stack.append(("block", tag))
            return
        if tag not in _SAFE_TAGS:
            self._stack.append(("drop", tag))
            return
        safe = self._safe_attrs(tag, dict(attrs))
        if tag in self.VOID:
            self.out.append(f"<{tag}{safe}>")
            return
        self.out.append(f"<{tag}{safe}>")
        self._stack.append(("emit", tag))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self._stack) - 1, -1, -1):
            mode, open_tag = self._stack[i]
            if open_tag != tag:
                continue
            if mode == "emit" and tag not in self.VOID:
                self.out.append(f"</{tag}>")
            del self._stack[i:]
            return

    def handle_data(self, data):
        if any(mode == "block" for mode, _ in self._stack):
            return
        self.out.append(data)

    def _safe_attrs(self, tag, attrs):
        safe = ""
        for key, val in attrs.items():
            key = key.lower()
            if key.startswith("on"):
                continue
            if key == "href":
                if safe_link(val):
                    safe += f' href="{val}"'
            elif key == "src" and tag == "img" and safe_link(val):
                safe += f' src="{val}"'
            elif key in {"title", "alt"}:
                safe += f' {key}="{val}"'
        return safe


def sanitize_html(raw: str) -> str:
    """Allowlist-sanitise trusted-but-not-clean HTML."""
    parser = _AllowlistParser()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.out)

# Storefront appearance -------------------------------------------------------
def default_storefront_design(config):
    from apps.storefront.themes import SECTIONS
    theme = config.theme or {}
    return {
        "theme": "classic", "font": "inherit", "density": "comfortable", "shape": "original",
        "hero_layout": "split", "menu_layout": "columns",
        "colors": {key: theme.get(key, fallback) for key, fallback in
                   (("brand", "#FF8507"), ("paper", "#FFFBF6"), ("ink", "#1A1410"), ("surface_alt", "#FFF3E4"))},
        "sections": [{"key": key, "enabled": True} for key, _, _ in SECTIONS],
    }


def validate_storefront_design(design):
    """Accept only registered layouts and six-digit colors; no HTML/CSS input."""
    import re
    from copy import deepcopy
    from django.core.exceptions import ValidationError
    from apps.storefront.themes import (THEMES, SECTIONS, FONT_CHOICES, DENSITY_CHOICES,
                                        SHAPE_CHOICES, HERO_CHOICES, MENU_CHOICES)
    if not isinstance(design, dict):
        raise ValidationError("Choose a valid storefront design.")
    for name, choices in (("theme", THEMES), ("font", dict(FONT_CHOICES)), ("density", dict(DENSITY_CHOICES)),
                          ("shape", dict(SHAPE_CHOICES)), ("hero_layout", dict(HERO_CHOICES)), ("menu_layout", dict(MENU_CHOICES))):
        if design.get(name) not in choices:
            raise ValidationError(f"Choose a valid {name.replace('_', ' ')}.")
    colors = design.get("colors")
    if not isinstance(colors, dict) or set(colors) != {"brand", "paper", "ink", "surface_alt"}:
        raise ValidationError("Choose all four storefront colors.")
    if any(not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in colors.values()):
        raise ValidationError("Use a six-digit hex color, such as #FF8507.")
    sections = design.get("sections")
    keys = {key for key, _, _ in SECTIONS}
    if (not isinstance(sections, list) or len(sections) != len(keys)
        or any(not isinstance(s, dict) or s.get("key") not in keys or type(s.get("enabled")) is not bool for s in sections)
        or {s["key"] for s in sections} != keys):
        raise ValidationError("Each home page section must appear exactly once.")
    if not any(s["enabled"] for s in sections):
        raise ValidationError("Keep at least one home page section visible.")
    # Avoid unreadable body copy. Button text is derived separately.
    def luminance(color):
        values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    ink = luminance(colors["ink"])
    if ink > .25 or any(luminance(colors[key]) < .75 for key in ("paper", "surface_alt")):
        raise ValidationError("Kitchen Classic uses light backgrounds and dark text. Choose pale backgrounds and darker text.")
    for key in ("paper", "surface_alt"):
        background = luminance(colors[key])
        if (max(ink, background) + .05) / (min(ink, background) + .05) < 4.5:
            raise ValidationError("Choose text and background colors with enough contrast to read clearly.")
    return deepcopy({key: design[key] for key in
                     ("theme", "font", "density", "shape", "hero_layout", "menu_layout", "colors", "sections")})


def storefront_design(config, *, draft=False):
    """No published snapshot means the existing tenant theme is unchanged."""
    from copy import deepcopy
    state = config.storefront_design or {}
    design = state.get("draft") if draft else state.get("published")
    if not design:
        design = state.get("published") or default_storefront_design(config)
    result = deepcopy(design)
    if state.get("published") and not (draft and state.get("draft")):
        result["colors"]["brand"] = (config.theme or {}).get("brand", result["colors"]["brand"])
    return result


def change_storefront_design(tenant, *, action, revision, design=None):
    from copy import deepcopy
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from apps.tenancy.models import TenantConfig
    if action not in {"save", "publish", "restore", "discard"}:
        raise ValidationError("Choose a valid appearance action.")
    if action in {"save", "publish"}:
        design = validate_storefront_design(design)
    with transaction.atomic():
        config = TenantConfig.objects.select_for_update().get(tenant=tenant)
        state = deepcopy(config.storefront_design or {})
        if revision != state.get("revision", 0):
            raise ValidationError("The appearance changed in another session. Reload this page before saving.")
        if action == "save":
            state["draft"] = design
        elif action == "publish":
            state["previous"] = storefront_design(config)
            state["published"] = design
            state.pop("draft", None)
        elif action == "restore":
            if not state.get("previous"):
                raise ValidationError("There is no previous published design to restore yet.")
            state["published"], state["previous"] = state["previous"], storefront_design(config)
            state.pop("draft", None)
        else:
            state.pop("draft", None)
        state["revision"] = state.get("revision", 0) + 1
        config.storefront_design = state
        fields = ["storefront_design"]
        if action in {"publish", "restore"}:
            # Keep the existing Store settings brand-color control consistent.
            config.theme = {**(config.theme or {}), "brand": state["published"]["colors"]["brand"]}
            fields.append("theme")
        config.save(update_fields=fields)
        return state


def storefront_appearance(request):
    """Resolve once per request; unpublished designs need this kitchen's access."""
    from django.core.exceptions import PermissionDenied
    from apps.owner.access import can_manage
    from apps.storefront.themes import SECTION_TEMPLATES
    if hasattr(request, "_storefront_appearance"):
        return request._storefront_appearance
    config = request.tenant.config
    home_path = getattr(request, "workspace_preview_url", "/")
    preview = request.path == home_path and request.GET.get("design") == "draft"
    if preview and not can_manage(request.user, request.tenant):
        raise PermissionDenied("Only this kitchen's team can preview its draft.")
    design = storefront_design(config, draft=preview)
    state = config.storefront_design or {}
    theme = dict(config.theme or {})
    if state.get("published") or (preview and state.get("draft")):
        theme.update(design["colors"])
        if not preview:
            theme["brand"] = (config.theme or {}).get("brand", design["colors"]["brand"])
        # Color choices also drive contrast-sensitive derived theme tokens.
        channels = [int(theme["brand"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        luminance = sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
        theme["on_brand"] = "#1A1410" if (luminance + .05) / .057 > 1.05 / (luminance + .05) else "#FFFFFF"
        if design["font"] != "inherit":
            theme["google_fonts"] = "Bricolage+Grotesque:wght@500;700;800&family=Figtree:wght@400;500;600;700"
            theme["font_body"] = 'Figtree,system-ui,sans-serif'
            theme["font_display"] = {'modern': 'Bricolage Grotesque,system-ui,sans-serif',
                                     'clean': 'system-ui,sans-serif', 'editorial': 'Georgia,serif'}[design["font"]]
            if design["font"] == "clean":
                theme["font_body"] = "system-ui,sans-serif"
    result = {"storefront_design": design, "storefront_theme": theme, "appearance_preview": preview,
              "storefront_sections": [{**section, "template": SECTION_TEMPLATES[section["key"]]}
                                      for section in design["sections"] if section["enabled"]]}
    request._storefront_appearance = result
    return result
