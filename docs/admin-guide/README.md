# Annam Foods staff guide

- [Download the editable Word document](Annam-Foods-Admin-Guide.docx)
- [Open the PDF copy](Annam-Foods-Admin-Guide.pdf)

This 30-page guide focuses on daily kitchen and website work. It contains 26
illustrated tasks, a page index, a daily checklist and common questions, written
in simple English for Annam’s staff.

It covers menus, products/photos, orders, offline payment confirmation, fulfilment,
bill printing, everyday WhatsApp inbox use, categories, meal times, meal delivery
areas, banners, pages and basic store contact/identity details.

At the user’s request, it excludes sign-in/sign-out instructions, Razorpay setup,
WhatsApp integration settings, shop courier settings, advanced tax configuration,
and technical ordering/backup setup. The application itself has not changed.
Actual screenshots can still show existing sidebar links; those setup screens
are not taught in this guide.

Screenshots were captured from the isolated PHP preview on 24 October 2026.
Customer/order examples are practice records. No live orders, real payments,
refunds, WhatsApp sends or production settings were changed to make this guide.
All pictures are embedded in the Word file, so it can be shared by itself. The
PDF is a fixed-layout viewing and printing copy.

## Updating the guide

`build_guide.py` contains the text and layout. After updating the relevant
screenshots, rebuild with Python, `python-docx` and Pillow:

```sh
python docs/admin-guide/build_guide.py
```

Export the Word file to PDF using Word or LibreOffice. Verify page references
against `guide-index.json` after every layout change.

The current version has 26 illustrated tasks, 30 pages, and 28 embedded pictures
including the logo and two bill details. Its page references, removed-topic
checks and embedded-image integrity were verified. The repository’s full Django
suite must pass before committing; no PHP application code changed for this
revision.
