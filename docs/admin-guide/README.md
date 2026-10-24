# Annam Foods admin user guide

- [Download the editable Word document](Annam-Foods-Admin-Guide.docx)
- [Open the PDF copy](Annam-Foods-Admin-Guide.pdf)

The 39-page guide includes screenshots for all 14 PHP admin tabs, 35 illustrated
walkthroughs, a page index, a daily kitchen checklist and common questions.
It is written in simple English for Annam’s staff and identifies owner-only
payment, billing and connection tasks.

Screenshots were captured from the isolated PHP preview on 24 October 2026.
Customer/order examples are practice records. No live orders, real payments,
refunds, WhatsApp sends or production settings were changed to make this guide.
All images are embedded in the Word file; it can be shared without the screenshot
folder. The PDF is supplied as a fixed-layout viewing/printing copy.

The guide follows `php-rebuild`; it does not certify live provider connections or
a production cutover. Menu dates, names, prices and counts shown in screenshots
may differ from the final store.

## Updating the guide

`build_guide.py` contains the instructional text and document layout. After
refreshing the relevant screenshots, run it with Python, `python-docx` and Pillow:

```sh
python docs/admin-guide/build_guide.py
```

Export the resulting Word file to PDF using Word or LibreOffice. If the number
of pages changes, review the contents-page references and `guide-index.json`.
The current PDF was checked: all 35 task references match their pages, all 39
pages contain content, and the Word file contains 37 embedded pictures including
the logo and two bill details. Representative pages were visually reviewed.

Repository verification before publishing: all 546 Django tests passed. This is
a documentation change; no PHP application code was changed for the guide.
