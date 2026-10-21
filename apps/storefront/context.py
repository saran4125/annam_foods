"""Template context every storefront page shares: is there a shop, what are
its shelves, and the WhatsApp contact link. Empty on the platform host."""


def storefront(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {}
    from apps.content.models import Page

    shop_enabled = tenant.feature("snacks_courier")
    shelves = []
    if shop_enabled:
        from apps.catalog.services import shop_categories

        shelves = shop_categories()
    from apps.content.services import storefront_appearance
    return {
        **storefront_appearance(request),
        "shop_enabled": shop_enabled,
        "nav_shelves": shelves,
        # The footer lists every published page; the header only show_in_nav ones.
        "footer_pages": Page.objects.filter(published=True),
    }
