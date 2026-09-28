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