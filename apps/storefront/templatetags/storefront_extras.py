from django import template

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
