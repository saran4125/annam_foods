from django.db import models

from apps.tenancy.managers import TenantOwnedModel


class DeliveryZone(TenantOwnedModel):
    """Where a kitchen delivers, and on what terms.

    One pincode can hold several areas with different fees, which is why the
    storefront sometimes has to ask which area the customer is in.
    """

    pincode = models.CharField(max_length=10, db_index=True)
    area_name = models.CharField(max_length=120)
    delivery_fee = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    min_order = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    slot_keys = models.JSONField(
        default=list, blank=True,
        help_text="Slots served here. Empty means every slot.",
    )
    active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["pincode", "area_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "pincode", "area_name"], name="uniq_zone_pincode_area"
            )
        ]

    def __str__(self):
        return f"{self.area_name} ({self.pincode})"

    def serves_slot(self, slot_key: str) -> bool:
        return not self.slot_keys or slot_key in self.slot_keys
