"""Meta's limits, enforced once in the app rather than per provider.

Every assertion here corresponds to a real Annam outage.
"""
import pytest

from apps.messaging import payloads as p


def test_cta_label_at_the_limit_is_accepted():
    assert p.cta_url("Order now", "https://x.in", "12345678901234567890")["label"]


def test_cta_label_one_over_the_limit_is_refused():
    """'Send Order via WhatsApp' was 26 characters and silently killed every
    Place Order tap for days. Fail while building, not at send time."""
    with pytest.raises(p.PayloadError, match="21 characters"):
        p.cta_url("Order now", "https://x.in", "123456789012345678901")


def test_the_label_that_actually_broke_annam_is_refused():
    with pytest.raises(p.PayloadError):
        p.cta_url("Place your order", "https://annamfood.in", "📱 Send Order via WhatsApp")


def test_three_buttons_are_allowed_and_four_are_not():
    p.buttons("Pick one", [("a", "A"), ("b", "B"), ("c", "C")])
    with pytest.raises(p.PayloadError, match="allows 3"):
        p.buttons("Pick one", [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")])


def test_button_title_length_is_checked():
    with pytest.raises(p.PayloadError, match="limit is 20"):
        p.buttons("Pick", [("a", "A" * 21)])


def test_list_rows_cap_at_ten():
    rows = [(f"i{n}", f"Item {n}", "") for n in range(10)]
    p.list_message("Menu", "View", [{"title": "Food", "rows": rows}])
    with pytest.raises(p.PayloadError, match="allows 10"):
        p.list_message("Menu", "View", [{"title": "Food", "rows": rows + [("x", "X", "")]}])


def test_empty_body_is_refused():
    with pytest.raises(p.PayloadError):
        p.text("   ")


def test_cta_url_requires_a_url():
    with pytest.raises(p.PayloadError):
        p.cta_url("Order", "", "Order now")


def test_a_valid_text_payload_is_provider_agnostic():
    """No Meta-specific keys leak into the payload — that's the sender's job."""
    payload = p.text("Hello")
    assert payload == {"kind": "text", "body": "Hello"}
    assert "messaging_product" not in payload
