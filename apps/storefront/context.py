"""Template context every storefront page shares: is there a shop, what are
its shelves, and the WhatsApp contact link. Empty on the platform host."""
import re


def storefront(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {}
    config = getattr(tenant, "config", None)
    phone = re.sub(r"\D", "", getattr(config, "support_phone", "") or "")
    if len(phone) == 10:  # a bare Indian mobile number
        phone = "91" + phone
    from apps.content.models import Page

    shop_enabled = tenant.feature("snacks_courier")
    shelves = []
    if shop_enabled:
        from apps.catalog.services import shop_categories

        shelves = shop_categories()
    return {
        "shop_enabled": shop_enabled,
        "nav_shelves": shelves,
        # The footer lists every published page; the header only show_in_nav ones.
        "footer_pages": Page.objects.filter(published=True),
        "whatsapp_link": f"https://wa.me/{phone}" if len(phone) >= 11 else "",
    }
