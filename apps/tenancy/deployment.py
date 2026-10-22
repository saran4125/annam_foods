"""Keep background work within the configured store without rewriting old data."""
from django.conf import settings


def deployment_rows(queryset, lookup='tenant__slug'):
    slug = getattr(settings, 'STORE_SLUG', '')
    return queryset.filter(**{lookup: slug}) if slug else queryset
