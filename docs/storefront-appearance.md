# Visual website editor

**Appearance** opens a live canvas of the current Kitchen Classic storefront:
`/manage/appearance/` or `/platform/workspaces/<slug>/manage/appearance/`.
This is a visual editor for the current responsive website theme, not an
unrestricted HTML editor or an unrelated poster-design application.

## Kitchen owner workflow

1. Click a headline, paragraph or button label on the website and type new
   words. The editing panel shows the same text. It also edits lists such as
   spotlight ingredients and the text for ordering steps.
2. Click a welcome, main offer, spotlight or logo image to upload a photo or
   reuse one from the kitchen's photo library. Website name is editable too.
3. Drag a section's handle in the section list, or drag the selected section's
   handle on the canvas. Keyboard users can focus a handle and use arrow keys.
   The eye control hides or shows a section without deleting its content.
4. Choose **Style** for colours, fonts, spacing, corners and layout variants.
   The canvas refreshes with unsaved changes. **Desktop / Phone** changes the
   preview size; on phones the content inspector opens as a bottom panel.
5. Use **Undo / Redo** to reverse unsaved edits. **Save draft** stores the draft;
   **Publish website** makes the submitted design and words public.
   **Open saved preview** displays the last saved draft, not unsaved canvas edits.
6. Previous-design controls restore the previous published snapshot or discard
   a saved draft. They do not change products, invoices or order records.

Catalog names, prices, availability, legal billing details, computed statistics
and checkout calculations remain authoritative operational data. Selecting a
catalog section offers its menu editor instead of creating conflicting text-only
prices. The main offer can be edited on canvas; additional promotions remain
in Offer banners. The header/footer and responsive section structures stay
within the theme's approved layouts.

## Draft privacy, validation and photos

- `TenantConfig.storefront_design` stores draft/published/previous snapshots,
  including plain-text overrides and photo references, plus an editor revision.
  Publishing locks the row and rejects stale edits from another session.
- Live rendering is an authenticated CSRF-protected POST. It returns trusted
  server-rendered HTML without saving or publishing. The iframe is sandboxed,
  blocks navigation, checkout and form submissions, and accepts messages only
  from its owning editor window and origin.
- Content keys, lengths, fonts, colours and section templates are allowlisted.
  Text is escaped when rendered. No user HTML, JavaScript or raw CSS is accepted.
- Draft previews require management access to that kitchen. Rendered drafts
  use `private, no-store` and `noindex, nofollow` and never become public solely
  because someone supplies `?design=draft`.
- Editor photos use the tenant-owned `StorefrontImage` model, migration
  `content.0002`. Verified JPG/PNG/WebP files (up to 3 MB / 25 megapixels) live in
  the database, so ephemeral media disks do not lose them. The library currently
  permits 100 photos per kitchen. Existing catalog/media uploads keep their
  original storage behavior.
- Photo URLs under `/platform/assets/<kitchen>/<uuid>/` are private until that
  exact kitchen publishes a design referencing the photo. Other kitchens cannot
  use private images in previews or published designs. MIME type comes from
  validated image bytes and responses use `nosniff` and `private, no-store`.

## Extension points

`apps/storefront/themes.py` registers the single theme, approved section
partials, editable copy fields and image roles. `apps/content/services.py`
validates snapshots, resolves existing content, publishes and validates uploads.
`visual-editor.js` manages the parent editor; `storefront-canvas.js` runs only
in authenticated canvas renders. Ordinary storefront pages load neither script.

Existing tenants keep their configured design and content until changes are
published. A second storefront design can later use this same model, editor,
content schema and operational backend through a second registered theme.
