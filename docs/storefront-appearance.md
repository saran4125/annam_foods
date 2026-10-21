# Storefront appearance: first theme

Kitchen Classic is the current storefront, extracted into trusted reusable
sections. This release does not add a second design or change an existing
kitchen until its team publishes an appearance.

Open **Appearance** in the kitchen admin (`/manage/appearance/`, or
`/platform/workspaces/<slug>/manage/appearance/`).

- Reorder all ten home sections using accessible up/down buttons, or unique
  numeric positions. Toggle visibility without deleting menus, pages or images.
- Choose colors, a registered font pairing, spacing, card corners, hero layout
  and daily menu layout. Classic supports light backgrounds with dark text;
  unreadable color combinations are rejected.
- **Save draft**, then **Preview draft**. Preview uses the last saved draft.
  Existing content editors still manage logos, hero text, banners and products.
- **Publish changes** publishes the submitted form. The public site and ordinary
  workspace preview use only the published design. Colors and typography apply
  to the storefront, while section arrangement applies to the home page.
- **Restore previous design** swaps the current and previous published designs.
  **Discard draft** removes unpublished design edits. Neither changes orders,
  products, payment settings or billing.

Draft home previews use `?design=draft`. They require authenticated management
access to that kitchen (or platform superuser access), use `private, no-store`
and `noindex, nofollow`, and are never activated merely by a customer query
parameter. Preview navigation returns to ordinary published storefront pages.

## Storage and extension

Migration `tenancy.0008` adds the non-destructive JSON field
`TenantConfig.storefront_design`. It holds draft/published/previous snapshots
and an editor revision. Writes lock the configuration row and reject stale
revisions. Existing `theme`, `home_sections`, uploads and content remain intact.
The old Store settings brand-color control stays effective after publication.

`apps/storefront/themes.py` registers the single theme, allowed options and ten
section templates. `apps/content/services.py` validates and publishes the design.
Templates come from this trusted registry, never from user-provided paths or
HTML/CSS. Add the second theme to this registry with its approved rendering and
options in the next phase; do not fork the code for a kitchen.

A hidden section with no content does not create placeholder products or fake
statistics. Operational feature switches continue to control shop availability
and website ordering independently of visual section settings.
