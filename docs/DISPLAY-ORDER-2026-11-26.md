# Display order — 26 November 2026

Product display order takes priority over category order in shop and owner lists.
Equal ranks sort by name and unique ID, preventing unstable pagination for items
with identical names/prices. The default Shop shelf includes every courier item,
including items assigned to custom categories. Home favourites are grouped first,
then ordered by saved rank; photo presence no longer overrides rank and favourites
are no longer restricted to the first 60 catalog records.

Local Chromium verification changed a Breakfast dish's rank from 1 to 20 through
the dated admin edit form and confirmed the new order in both the admin list and
public menu for that date. That reported save failure did not reproduce locally.
A regression test covers the exact POST and resolved customer menu. Numeric ranks
are ascending: lower numbers first; equal numbers are alphabetical. Stock and
daily availability still independently determine whether an item can be shown.
