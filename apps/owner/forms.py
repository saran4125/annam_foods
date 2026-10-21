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


class BillingSettingsForm(StyledForm):
    class Meta:
        from apps.tenancy.models import BillingProfile
        model = BillingProfile
        fields = ["legal_name", "address", "state", "state_code", "fssai_no", "invoice_prefix",
                  "gst_mode", "gstin", "tax_rate", "sac", "prices_include_tax", "round_total",
                  "delivery_fee_taxable", "footer"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "footer": forms.Textarea(attrs={"rows": 2})}
        labels = {"fssai_no": "FSSAI number", "gstin": "GSTIN", "sac": "SAC / HSN code"}

    def clean(self):
        from apps.billing.services import validate_billing_profile
        data = super().clean()
        if self.errors:
            return data
        from copy import copy
        profile = copy(self.instance)
        for field, value in data.items():
            setattr(profile, field, value)
        profile.bill_timing = "on_payment"
        try:
            validate_billing_profile(profile)
        except (ValueError, ValidationError) as exc:
            raise ValidationError(" ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)) from exc
        return data


class AppearanceForm(forms.Form):
    from apps.storefront.themes import FONT_CHOICES, DENSITY_CHOICES, SHAPE_CHOICES, HERO_CHOICES, MENU_CHOICES
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    font = forms.ChoiceField(choices=FONT_CHOICES, label="Font style")
    density = forms.ChoiceField(choices=DENSITY_CHOICES, label="Space between sections")
    shape = forms.ChoiceField(choices=SHAPE_CHOICES, label="Corner style")
    hero_layout = forms.ChoiceField(choices=HERO_CHOICES, label="Welcome layout")
    menu_layout = forms.ChoiceField(choices=MENU_CHOICES, label="Menu arrangement")
    brand = forms.RegexField(r"^#[0-9a-fA-F]{6}$", label="Brand colour", widget=forms.TextInput(attrs={"type": "color"}))
    paper = forms.RegexField(r"^#[0-9a-fA-F]{6}$", label="Page background", widget=forms.TextInput(attrs={"type": "color"}))
    ink = forms.RegexField(r"^#[0-9a-fA-F]{6}$", label="Main text", widget=forms.TextInput(attrs={"type": "color"}))
    surface_alt = forms.RegexField(r"^#[0-9a-fA-F]{6}$", label="Feature backgrounds", widget=forms.TextInput(attrs={"type": "color"}))

    def __init__(self, *args, design, revision=0, config=None, **kwargs):
        from apps.storefront.themes import SECTIONS
        initial = {key: design[key] for key in ("font", "density", "shape", "hero_layout", "menu_layout")}
        initial.update(design["colors"])
        initial["revision"] = revision
        initial.update({f"show_{s['key']}": s["enabled"] for s in design["sections"]})
        initial.update({f"order_{s['key']}": i for i, s in enumerate(design["sections"], 1)})
        super().__init__(*args, initial=initial, **kwargs)
        from apps.storefront.themes import COPY_FIELDS, IMAGE_FIELDS
        from apps.content.services import storefront_copy_defaults
        self.copy_defaults = storefront_copy_defaults(config) if config else {key: value[2] for key, value in COPY_FIELDS.items()}
        self.old_content = design.get('content', {})
        self.old_images = design.get('images', {})
        self.content_groups = []
        for section, section_label, _ in (*SECTIONS, ("brand", "Your brand", ""), ("footer", "Footer & business details", "")):
            fields = []
            for key, (label, limit, _) in COPY_FIELDS.items():
                if key.split('.')[0] != section:
                    continue
                name = 'copy_' + key
                self.fields[name] = forms.CharField(required=False, max_length=limit, label=label,
                    initial=self.old_content.get(key, self.copy_defaults[key]),
                    widget=forms.Textarea(attrs={'rows': 3 if limit > 300 else 2}) if limit > 300 or key.endswith('.title') else forms.TextInput())
                fields.append({'key': key, 'field': self[name]})
            self.content_groups.append({'key': section, 'label': section_label, 'fields': fields})
        self.image_fields = []
        for key, label in IMAGE_FIELDS.items():
            name = 'image_' + key
            self.fields[name] = forms.CharField(required=False, widget=forms.HiddenInput,
                                               initial=self.old_images.get(key, ''))
            self.image_fields.append({'key': key, 'label': label, 'field': self[name]})
        labels = {key: (label, description) for key, label, description in SECTIONS}
        self.section_rows = []
        for section in design["sections"]:
            key = section["key"]
            self.fields[f"show_{key}"] = forms.BooleanField(required=False, label=f"Show {labels[key][0]}")
            self.fields[f"order_{key}"] = forms.IntegerField(min_value=1, max_value=len(SECTIONS), label=f"Position of {labels[key][0]}")
            self.section_rows.append({"key": key, "label": labels[key][0], "description": labels[key][1],
                                      "visible": self[f"show_{key}"], "position": self[f"order_{key}"]})
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.HiddenInput, forms.CheckboxInput)):
                field.widget.attrs.setdefault("class", "o-input")

    def clean(self):
        from apps.content.services import validate_storefront_design
        from apps.storefront.themes import SECTIONS
        data = super().clean()
        if self.errors:
            return data
        positions = [data[f"order_{key}"] for key, _, _ in SECTIONS]
        if len(set(positions)) != len(positions):
            raise ValidationError("Give each section a different position, from 1 to 10.")
        design = {key: data[key] for key in ("font", "density", "shape", "hero_layout", "menu_layout")}
        design.update(theme="classic", colors={key: data[key] for key in ("brand", "paper", "ink", "surface_alt")},
                      sections=[{"key": key, "enabled": data[f"show_{key}"]}
                                for key, _, _ in sorted(SECTIONS, key=lambda section: data[f"order_{section[0]}"])])
        content, images = dict(self.old_content), dict(self.old_images)
        from apps.storefront.themes import COPY_FIELDS, IMAGE_FIELDS
        for key in COPY_FIELDS:
            name = 'copy_' + key
            if name in self.data:
                value = data[name]
                if value != self.copy_defaults[key]:
                    content[key] = value
                else:
                    content.pop(key, None)
        for key in IMAGE_FIELDS:
            name = 'image_' + key
            if name in self.data:
                if data[name]:
                    images[key] = data[name]
                else:
                    images.pop(key, None)
        design.update(content=content, images=images)
        data["design"] = validate_storefront_design(design)
        return data
