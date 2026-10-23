# Approved Annam meal delivery coverage

Source: the user's `Annam_Foods_Delivery_Zones.csv`, exported on 22 October 2026.
The original file is retained in `deploy/annam_meal_delivery_zones.csv`.

The file contains **63 active zones across 61 pincodes**:

| Meal/type | Served zones |
| --- | ---: |
| Breakfast | 12 |
| Lunch | 63 |
| Dinner | 38 |
| Snacks | 63 |

Every row's fee, minimum and Yes/No meal flags are imported exactly. In
particular, 600005 has a ₹10 delivery charge and ₹100 minimum; 600086's minimum
is ₹30 as supplied. No pincode-prefix coverage is inferred.

Two pincodes require an area choice:

| Pincode | Area | Delivery charge | Minimum |
| --- | --- | ---: | ---: |
| 600083 | Ashok Nagar | ₹40 | ₹100 |
| 600083 | Jaffar Khan Pet | ₹60 | ₹100 |
| 600100 | Medavakkam | ₹60 | ₹320 |
| 600100 | Perumbakalm | ₹100 | ₹320 |

Area spelling follows the source. An em dash in the file means no area name was
provided; preserve an existing useful area name where unambiguous, otherwise
use “Delivery area”. These are not additional subareas or guessed geocoding.

The one-time deployment migration updates Annam's meal zones, retains matching
zone IDs where possible, and deactivates old zones outside the supplied list
rather than deleting them. It does not touch another store, shop courier
coverage, existing order/invoice snapshots or menu availability. Later owner
edits are not overwritten on every restart. Fresh seeding uses the same CSV.

The Snacks flag is preserved even if no Snacks menu slot is configured. Importing
coverage does not create a Snacks menu or change any dish's availability. The
zone editor retains such imported flags during edits.

Review/edit rules in **Admin → Delivery areas**. Meal eligibility, area choice,
minimum subtotal and delivery fees are enforced by the existing checkout and
order services. Courier products keep their separate Checkout & courier rules.
