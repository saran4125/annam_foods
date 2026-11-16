import io

from django.core.management import call_command

from apps.catalog.models import MenuItem
from apps.content.models import Banner
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig
from .test_storefront import HOST, kitchen, menu  # noqa: F401


def test_owner_photo_order_overrides_meals_and_sweets_without_changing_offer_banner(client, kitchen, menu):
    with tenant_context(kitchen):
        products = [MenuItem.objects.create(
            name=name, retailer_id=key, fulfilment='courier', price=100,
            image=f'catalog/{key}.jpg', sort=index,
        ) for index, (key, name) in enumerate([
            ('KEI1', 'Karuppu Ellu Idly Podi'), ('MRP1', 'Mysore Rasam Podi'),
            ('PP2', 'Pirandai Podi'), ('PT4', 'Pirandai Thuvaiyal'),
        ])]
        Banner.objects.create(title='Diwali offer', image='banners/diwali.jpg', link='/shop/')
    TenantConfig.objects.filter(tenant=kitchen).update(theme={'brand': '#123456'})
    call_command('configure_hero_products', stdout=io.StringIO())
    response = client.get('/', HTTP_HOST=HOST)
    assert response.status_code == 200
    assert [p.pk for p in response.context['hero_picks']] == [p.pk for p in products]
    assert b'/media/catalog/KEI1.jpg' in response.content
    assert b'/media/banners/diwali.jpg' in response.content
    with tenant_context(kitchen):
        assert Banner.objects.get().image.name == 'banners/diwali.jpg'
        assert MenuItem.objects.get(pk=products[0].pk).price == 100
    config = TenantConfig.objects.get(tenant=kitchen)
    assert config.theme['brand'] == '#123456'
    # Restarts must preserve later owner changes to the selected photos.
    config.theme['hero_product_ids'] = ['PT4']
    config.save(update_fields=['theme'])
    call_command('configure_hero_products', stdout=io.StringIO())
    config.refresh_from_db()
    assert config.theme['hero_product_ids'] == ['PT4']
