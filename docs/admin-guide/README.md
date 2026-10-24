# Annam Foods staff quick guide

- [Download Word](Annam-Foods-Admin-Guide.docx)
- [Open PDF](Annam-Foods-Admin-Guide.pdf)

**11 tabs, 11 pages.** Each page has a tab name, one-sentence purpose, one real
screenshot and four short explanations of the main controls. There is no cover,
contents page, lengthy walkthrough, repeated subpage or troubleshooting chapter.

The tabs are Dashboard, Orders & billing, WhatsApp inbox, Dishes & products,
Daily menus, Categories, Meal times, Delivery areas, Offer banners, Website pages
and Store settings.

Technical integration settings, payment-provider setup, courier configuration,
advanced tax/backup setup and sign-in/sign-out instructions remain excluded.
The application itself has not changed.

Screenshots show the actual working areas of the isolated PHP preview, using
practice records. No production data, real payment or WhatsApp send was changed
for these documents. All screenshots are embedded in the Word file.

## Rebuild

`build_guide.py` contains the short text and layout. With `python-docx` installed:

```sh
python docs/admin-guide/build_guide.py
```

Export the Word file to PDF using Word or LibreOffice. Check that the PDF has
exactly 11 pages and matches `guide-index.json`.

Validation: 11 pages, 11 embedded screenshots, one drawn screenshot per PDF page,
matching tab/page headings, and fewer than 110 words per page. Representative
pages were visually checked. The repository’s 546 Django tests passed before
publishing this documentation-only update.
