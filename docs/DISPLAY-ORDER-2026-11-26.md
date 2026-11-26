# Display order — 26 November 2026

Product display order takes priority over category order in shop and owner lists.
Equal ranks now put the most recently saved Display order first, with name and
unique ID as a stable fallback for old unassigned records. The default Shop shelf includes every courier item,
including items assigned to custom categories. Home favourites are grouped first,
then ordered by saved rank; photo presence no longer overrides rank and favourites
are no longer restricted to the first 60 catalog records.

Local Chromium verification changed a Breakfast dish's rank from 1 to 20 through
the dated admin edit form and confirmed the new order in both the admin list and
public menu for that date. That reported save failure did not reproduce locally.
A regression test covers the exact POST and resolved customer menu. Numeric ranks
are ascending: lower numbers first; equal numbers use the most recent display-order save. Stock and
daily availability still independently determine whether an item can be shown.

A dedicated sort_priority field records explicit dish-form saves only. Stock,
orders and availability changes never refresh that priority. Existing rows start
at zero; no historical edits are guessed. Browser tests cover repeatedly saving
rank 1 in both versions, including resaving an unchanged number.
