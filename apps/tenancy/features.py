"""The complete, typed registry of tenant feature switches."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    default: bool
    description: str


FEATURES = {
    "website_ordering": Feature(True, "Allow storefront checkout"),
    "whatsapp_chat_ordering": Feature(True, "Guided WhatsApp orders"),
    "whatsapp_catalog_ordering": Feature(False, "Accept Meta catalog carts"),
    "whatsapp_catalog_sync": Feature(False, "Publish catalog to Meta"),
    "native_whatsapp_pay": Feature(False, "Pay within WhatsApp"),
    "cod": Feature(False, "Cash on delivery"),
    "manual_payments": Feature(True, "Owner-recorded offline payments"),
    "snacks_courier": Feature(False, "Courier-fulfilled goods"),
    "seasonal_offers": Feature(False, "Seasonal collections"),
    "invoice_on_request": Feature(True, "Chat bill requests"),
    "owner_whatsapp_commands": Feature(False, "Owner commands in WhatsApp"),
    "notify_preparing": Feature(False, "Preparing update"),
    "notify_confirmed": Feature(False, "Confirmation update"),
    "owner_copy_of_bill": Feature(True, "Owner bill copy"),
    "reorder_prompt": Feature(True, "Order again prompt"),
    "language_ta": Feature(False, "Tamil copy"),
}


def validate_features(values: dict) -> dict:
    if not isinstance(values, dict):
        raise ValueError("Features must be a mapping.")
    unknown = set(values) - set(FEATURES)
    if unknown:
        raise ValueError("Unknown feature flag: " + ", ".join(sorted(unknown)))
    if any(type(value) is not bool for value in values.values()):
        raise ValueError("Every feature value must be a boolean.")
    return values
