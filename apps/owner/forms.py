"""Forms the kitchen owner edits their store with.

Every queryset is re-read inside __init__, i.e. inside the request's tenant
context, so a dropdown can only ever offer this kitchen's own rows.
"""
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import capfirst, slugify

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.content.models import Banner, Page
from apps.content.services import safe_link
from apps.delivery.models import DeliveryZone

MAX_IMAGE_BYTES = 5 * 1024 * 1024
WEEKDAYS = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun")]


def _check_image(image):
    if image and hasattr(image, "size") and image.size > MAX_IMAGE_BYTES:
        raise ValidationError("Images must be 5 MB or smaller.")
    return image


def scoped_formfield(db_field, **kwargs):
    """Build foreign-key fields without touching the tenant-scoped manager.

    Django builds a ModelForm's FK querysets when the form *class* is created,
    at import time, where there is no tenant -- and our managers fail closed.
    FK fields start empty here; each form's __init__ sets the real queryset
    inside the request's tenant context."""
    if isinstance(db_field, models.ForeignKey):
        options = {"label": capfirst(db_field.verbose_name), "help_text": db_field.help_text}
        options.update({k: v for k, v in kwargs.items() if k in ("label", "help_text", "widget")})
        return forms.ModelChoiceField(
            queryset=db_field.remote_field.model.all_tenants.none(),
            required=not db_field.blank, **options,
        )
    return db_field.formfield(**kwargs)


class BaseMeta:
    formfield_callback = scoped_formfield


class StyledForm(forms.ModelForm):
    """Adds the owner-theme classes so templates can render fields generically."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            widget.attrs.setdefault("class", "o-input")


class DishForm(StyledForm):
    featured = forms.BooleanField(required=False, help_text="Show in “Popular in the shop” on the home page.")
    slot = forms.ModelChoiceField(queryset=Slot.all_tenants.none(), required=False,  # real queryset set per request
                                  help_text="Daily meals only: which meal this dish is served at.")
    weekdays = forms.TypedMultipleChoiceField(
        choices=WEEKDAYS, coerce=int, required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Daily meals only: the days it is on the menu every week.",
    )

    class Meta(BaseMeta):
        model = MenuItem
        fields = ["name", "category", "fulfilment", "price", "description", "image",
                  "is_veg", "active", "sort"]
        labels = {"fulfilment": "Type", "is_veg": "Vegetarian", "active": "On sale",
                  "sort": "Display order"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"fulfilment": "Daily meal = cooked for a slot. Shop item = packed and shipped.",
                      "active": "Untick to hide it from the website (sold out, seasonal…)."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fulfilment"].choices = [("scheduled", "Daily meal"), ("courier", "Shop item")]
        self.fields["category"].queryset = MenuCategory.objects.all()
        self.fields["slot"].queryset = Slot.objects.all()
        self.fields["slot"].widget.attrs["class"] = "o-input"
        if self.instance.pk:
            self.fields["featured"].initial = "featured" in (self.instance.tags or [])
            rows = MenuSchedule.objects.filter(item=self.instance, mode=ScheduleMode.WEEKDAY)
            first = rows.first()
            if first:
                self.fields["slot"].initial = first.slot_id
                self.fields["weekdays"].initial = sorted(
                    rows.filter(slot=first.slot).values_list("weekday", flat=True))
        else:
            self.fields["weekdays"].initial = [0, 1, 2, 3, 4, 5, 6]

    def clean_image(self):
        return _check_image(self.cleaned_data.get("image"))

    def clean(self):
        data = super().clean()
        if data.get("fulfilment") == "scheduled" and data.get("weekdays") and not data.get("slot"):
            self.add_error("slot", "Choose the meal this dish is served at.")
        return data

    def save(self, commit=True):
        item = super().save(commit=False)
        tags = [t for t in (item.tags or []) if t != "featured"]
        if self.cleaned_data.get("featured"):
            tags.append("featured")
        item.tags = tags
        item.save()
        self._sync_schedule(item)
        return item

    def _sync_schedule(self, item):
        """Weekly menu rows follow the form; dated overrides are left alone."""
        weekly = MenuSchedule.objects.filter(item=item, mode=ScheduleMode.WEEKDAY)
        slot = self.cleaned_data.get("slot")
        days = set(self.cleaned_data.get("weekdays") or [])
        if item.fulfilment != "scheduled" or not slot:
            weekly.delete()
            return
        weekly.exclude(slot=slot).delete()
        weekly.filter(slot=slot).exclude(weekday__in=days).delete()
        have = set(weekly.filter(slot=slot).values_list("weekday", flat=True))
        for day in sorted(days - have):
            MenuSchedule.objects.create(item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=day)


class CategoryForm(StyledForm):
    class Meta(BaseMeta):
        model = MenuCategory
        fields = ["name", "slug", "parent", "description", "image", "sort", "active"]
        labels = {"parent": "Inside category", "sort": "Display order", "active": "Visible"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"slug": "The web address, e.g. /shop/podi/. Leave blank to make one from the name."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        others = MenuCategory.objects.all()
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = others
        self.fields["slug"].required = False

    def clean_image(self):
        return _check_image(self.cleaned_data.get("image"))

    def clean_slug(self):
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("name") or "")[:80]
        if not slug:
            slug = slugify(self.data.get("name", ""))[:80]
        clash = MenuCategory.objects.filter(slug=slug)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if slug and clash.exists():
            raise ValidationError("Another category already uses this web address.")
        return slug

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        seen, node = set(), parent
        while node is not None and self.instance.pk:
            if node.pk == self.instance.pk or node.pk in seen:
                raise ValidationError("A category can’t sit inside itself.")
            seen.add(node.pk)
            node = node.parent
        return parent


class SlotForm(StyledForm):
    class Meta(BaseMeta):
        model = Slot
        fields = ["label", "key", "order_cutoff", "delivery_from", "delivery_to", "sort", "active"]
        labels = {"label": "Meal name", "key": "Short code", "order_cutoff": "Orders close at",
                  "sort": "Display order"}
        widgets = {f: forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
                   for f in ("order_cutoff", "delivery_from", "delivery_to")}
        help_texts = {"key": "Lowercase, no spaces, e.g. breakfast."}


class BannerForm(StyledForm):
    class Meta(BaseMeta):
        model = Banner
        fields = ["title", "subtitle", "image", "link", "sort", "active"]
        labels = {"sort": "Display order", "active": "Showing"}
        help_texts = {"image": "Wide artwork, about 1920 × 680. The first three showing banners rotate in the offers slider.",
                      "link": "Where a tap goes, e.g. /shop/sweets/ or /menu/."}

    def clean_image(self):
        return _check_image(self.cleaned_data.get("image"))

    def clean_link(self):
        link = (self.cleaned_data.get("link") or "").strip()
        if link and not safe_link(link):
            raise ValidationError("Use a page on this site (starting with /) or an https:// link.")
        return link


class PageForm(StyledForm):
    class Meta(BaseMeta):
        model = Page
        fields = ["title", "slug", "body_md", "seo_description", "published", "show_in_nav", "sort"]
        labels = {"body_md": "Content", "seo_description": "Search description",
                  "show_in_nav": "Show in top menu", "sort": "Display order"}
        widgets = {"body_md": forms.Textarea(attrs={"rows": 12})}
        help_texts = {"body_md": "Write normally. **bold**, - lists and [links](/shop/) work."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = slugify(self.cleaned_data.get("slug") or self.data.get("title", ""))[:80]
        clash = Page.objects.filter(slug=slug)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("Another page already uses this web address.")
        return slug


class ZoneForm(StyledForm):
    slot_keys = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple,
                                          label="Meals delivered here",
                                          help_text="Leave all unticked to deliver every meal here.")

    class Meta(BaseMeta):
        model = DeliveryZone
        fields = ["pincode", "area_name", "delivery_fee", "min_order", "slot_keys", "active"]
        labels = {"min_order": "Minimum order", "active": "Delivering"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slot_keys"].choices = [(s.key, s.label) for s in Slot.objects.all()]

    def clean_pincode(self):
        pincode = re.sub(r"\D", "", self.cleaned_data.get("pincode", ""))
        if len(pincode) != 6:
            raise ValidationError("Enter a 6-digit pincode.")
        return pincode


class SettingsForm(forms.Form):
    """Store identity and the home page hero. Stored on TenantConfig."""

    brand_name = forms.CharField(max_length=120, label="Store name")
    tagline = forms.CharField(max_length=200, required=False)
    support_phone = forms.CharField(max_length=20, required=False, label="Phone / WhatsApp")
    contact_email = forms.EmailField(required=False, label="Email")
    brand_color = forms.CharField(max_length=7, label="Brand colour",
                                  widget=forms.TextInput(attrs={"type": "color"}))
    logo = forms.ImageField(required=False, help_text="PNG or JPG, 5 MB max.")
    announcements = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}),
                                    help_text="One message per line. They scroll in the strip at the top.")
    hero_kicker = forms.CharField(max_length=80, required=False, label="Hero: small heading")
    hero_title = forms.CharField(max_length=120, required=False, label="Hero: headline")
    hero_body = forms.CharField(max_length=300, required=False, label="Hero: text",
                                widget=forms.Textarea(attrs={"rows": 3}))
    website_ordering = forms.BooleanField(required=False, label="Take orders on the website")
    snacks_courier = forms.BooleanField(required=False, label="Run the shop (shipped goods)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput) and name != "brand_color":
                field.widget.attrs.setdefault("class", "o-input")

    def clean_brand_color(self):
        value = self.cleaned_data["brand_color"]
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value or ""):
            raise ValidationError("Pick a colour.")
        return value

    def clean_logo(self):
        return _check_image(self.cleaned_data.get("logo"))
