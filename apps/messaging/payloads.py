"""Provider-agnostic message descriptions.

A payload says *what* to send, never *how*. Senders translate it for whichever
API is actually delivering.

Meta's limits are validated here, once, rather than in each sender -- so the
rules hold whether a message goes out through the Graph API directly or via
n8n. Every one of these limits cost Annam a live outage.
"""
from dataclasses import dataclass, field
from typing import Literal

# Meta's hard limits. Exceeding any of these is rejected at send time with an
# error most people never see, because the failing node dies quietly.
CTA_LABEL_MAX = 20      # a 26-char label broke every "Place Order" tap for days
BUTTON_TITLE_MAX = 20
BUTTON_MAX_COUNT = 3
LIST_ROW_MAX = 10
LIST_TITLE_MAX = 24
BODY_MAX = 1024


class PayloadError(ValueError):
    """A message that Meta would reject. Raised while building, not sending."""


def _body(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise PayloadError("Message body cannot be empty.")
    if len(text) > BODY_MAX:
        raise PayloadError(f"Body is {len(text)} characters; the limit is {BODY_MAX}.")
    return text


def text(body: str) -> dict:
    return {"kind": "text", "body": _body(body)}


def buttons(body: str, options: list[tuple[str, str]]) -> dict:
    """Reply buttons. `options` is [(id, title), ...], at most three."""
    if not options:
        raise PayloadError("A button message needs at least one button.")
    if len(options) > BUTTON_MAX_COUNT:
        raise PayloadError(
            f"{len(options)} buttons requested; WhatsApp allows {BUTTON_MAX_COUNT}."
        )
    for _id, title in options:
        if len(title) > BUTTON_TITLE_MAX:
            raise PayloadError(
                f"Button title {title!r} is {len(title)} characters; "
                f"the limit is {BUTTON_TITLE_MAX}."
            )
    return {
        "kind": "buttons",
        "body": _body(body),
        "buttons": [{"id": i, "title": t} for i, t in options],
    }


def cta_url(body: str, url: str, label: str) -> dict:
    """A single link button. Exactly one URL per message -- this is why an
    offer with two links has to be a choice, not both links at once."""
    if not url:
        raise PayloadError("A cta_url message needs a URL.")
    if len(label) > CTA_LABEL_MAX:
        raise PayloadError(
            f"Button label {label!r} is {len(label)} characters; "
            f"WhatsApp allows {CTA_LABEL_MAX}."
        )
    return {"kind": "cta_url", "body": _body(body), "url": url, "label": label}


def list_message(body: str, button: str, sections: list[dict]) -> dict:
    """`sections` is [{"title": str, "rows": [(id, title, description), ...]}]"""
    rows_total = sum(len(s.get("rows", [])) for s in sections)
    if rows_total == 0:
        raise PayloadError("A list message needs at least one row.")
    if rows_total > LIST_ROW_MAX:
        raise PayloadError(
            f"{rows_total} rows requested; WhatsApp allows {LIST_ROW_MAX}."
        )
    for section in sections:
        for row in section.get("rows", []):
            if len(row[1]) > LIST_TITLE_MAX:
                raise PayloadError(
                    f"Row title {row[1]!r} is {len(row[1])} characters; "
                    f"the limit is {LIST_TITLE_MAX}."
                )
    return {
        "kind": "list",
        "body": _body(body),
        "button": button[:BUTTON_TITLE_MAX],
        "sections": [
            {
                "title": s.get("title", ""),
                "rows": [
                    {"id": r[0], "title": r[1], "description": (r[2] if len(r) > 2 else "")}
                    for r in s.get("rows", [])
                ],
            }
            for s in sections
        ],
    }


def document(url: str, filename: str, caption: str = "") -> dict:
    """Used for invoice PDFs."""
    if not url:
        raise PayloadError("A document message needs a URL.")
    return {"kind": "document", "url": url, "filename": filename, "caption": caption}


def template(name: str, language: str = "en", params: list[str] | None = None) -> dict:
    """The only thing that reaches a customer outside the 24-hour window."""
    if not name:
        raise PayloadError("A template message needs a template name.")
    return {
        "kind": "template",
        "name": name,
        "language": language,
        "params": list(params or []),
    }
