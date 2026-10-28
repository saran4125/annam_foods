"""Category item management reuses the catalog controls within a fixed category."""
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from apps.catalog.models import MenuCategory, MenuItem
from .access import owner_required
from . import views


def selected_category(pk, item_pk=None):
    category = get_object_or_404(MenuCategory, pk=pk)
    if item_pk is not None:
        get_object_or_404(MenuItem, pk=item_pk, category=category)
    return category


@owner_required
def items(request, pk):
    return views.resource_list(request, 'dishes', category=selected_category(pk))


@owner_required
def item_new(request, pk):
    return views.resource_edit(request, 'dishes', category=selected_category(pk))


@owner_required
def item_edit(request, pk, item_pk):
    return views.resource_edit(request, 'dishes', pk=item_pk, category=selected_category(pk, item_pk))


@owner_required
def item_delete(request, pk, item_pk):
    return views.resource_delete(request, 'dishes', pk=item_pk, category=selected_category(pk, item_pk))


@owner_required
@require_POST
def item_toggle(request, pk, item_pk):
    category = selected_category(pk, item_pk)
    return views.resource_toggle(request, 'dishes', pk=item_pk, category=category)
