from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.tenancy.managers import TenantOwnedModel


class Slot(TenantOwnedModel):
    """A meal window. Each kitchen defines its own — most run breakfast,
    lunch and dinner; some add snacks or run a single all-day slot."""

    key = models.SlugField(max_length=30)
    label = models.CharField(max_length=60)
    order_cutoff = models.TimeField(
        help_text="Latest local time an order for this slot can be placed."
    )
    delivery_from = models.TimeField(null=True, blank=True)
    delivery_to = models.TimeField(null=True, blank=True)
    sort = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["sort", "key"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uniq_tenant_slot_key")
        ]

    def __str__(self):
        return self.label


class MenuCategory(TenantOwnedModel):
    name = models.CharField(max_length=80)
    sort = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["sort", "name"]
        verbose_name_plural = "menu categories"

    def __str__(self):
        return self.name


class MenuItem(TenantOwnedModel):
    """A dish the kitchen can sell. Whether it's on sale on a given day is
    decided by MenuSchedule, not here."""

    category = models.ForeignKey(
        MenuCategory, on_delete=models.PROTECT, related_name="items", null=True, blank=True
    )
    name = models.CharField(max_length=120)
    retailer_id = models.CharField(max_length=80, null=True, blank=True)
    fulfilment = models.CharField(max_length=12, choices=[("scheduled", "Scheduled meal"), ("courier", "Courier goods")], default="scheduled")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sac = models.CharField(max_length=12, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to="menu/", blank=True)
    is_veg = models.BooleanField(default=True)
    tags = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["sort", "name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "retailer_id"], name="uniq_tenant_retailer_id")]

    def __str__(self):
        return self.name


class ScheduleMode(models.TextChoices):
    DATE = "date", "This specific date"
    WEEKDAY = "weekday", "Every week on this day"


class MenuSchedule(TenantOwnedModel):
    """When an item is on the menu.

    Two kinds of row, and the difference is the whole design:

      mode='weekday'  a standing template — "idly every Monday breakfast"
      mode='date'     one specific day — "no idly on 2 October"

    Resolution looks for a date row first and falls back to the weekday row.
    That single rule gives three behaviours from one table: kitchens that plan
    by week, kitchens that decide each morning, and a weekly kitchen overriding
    one day without disturbing its template.

    `TenantConfig.menu_mode` only decides which editor the owner is shown. The
    resolver always consults both.
    """

    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="schedule")
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="schedule")
    mode = models.CharField(max_length=10, choices=ScheduleMode.choices)

    on_date = models.DateField(null=True, blank=True)
    weekday = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="Monday=0 … Sunday=6, matching Python's date.weekday().",
    )

    available = models.BooleanField(default=True)
    qty_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Blank means unlimited."
    )
    qty_sold = models.PositiveIntegerField(default=0)
    price_override = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta(TenantOwnedModel.Meta):
        ordering = ["slot__sort", "item__sort"]
        constraints = [
            # A row is either dated or weekly. Never both, never neither.
            models.CheckConstraint(
                condition=(
                    models.Q(mode="date", on_date__isnull=False, weekday__isnull=True)
                    | models.Q(mode="weekday", weekday__isnull=False, on_date__isnull=True)
                ),
                name="schedule_mode_matches_its_field",
            ),
            models.UniqueConstraint(
                fields=["tenant", "item", "slot", "on_date"],
                condition=models.Q(mode="date"),
                name="uniq_dated_schedule_row",
            ),
            models.UniqueConstraint(
                fields=["tenant", "item", "slot", "weekday"],
                condition=models.Q(mode="weekday"),
                name="uniq_weekly_schedule_row",
            ),
        ]

    def __str__(self):
        when = self.on_date if self.mode == ScheduleMode.DATE else f"weekday {self.weekday}"
        return f"{self.item} / {self.slot} / {when}"

    @property
    def is_sold_out(self) -> bool:
        return self.qty_limit is not None and self.qty_sold >= self.qty_limit

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.item.price

    @property
    def is_on_sale(self) -> bool:
        return self.available and self.item.active and not self.is_sold_out
