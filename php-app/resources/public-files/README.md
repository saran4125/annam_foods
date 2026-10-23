# Bundled public media recovery

Files here mirror legacy `/media/` paths and are used only when the actual
upload is absent. Recovery copies the file into MEDIA_ROOT before serving it.
An existing upload takes precedence. They are committed with
the application and require neither seed credentials nor a network download.
Only intentionally public catalog artwork belongs here; never private files.

`brand/annam-bill-logo.png` is the supplied bill logo. Bills now render it at
`/media/brand/annam-bill-logo.png`; the original static copy remains available
for old saved HTML files. Legacy editor files are stored in media/website/ and
require their access-controlled endpoint; they cannot be fetched via /media/.

`menu/9c83d9e7554c03d281561c7a.jpg` is newly generated illustrative Health Mix
artwork showing grain porridge, millets, rice, pulses and nuts. It replaces the
unavailable imported Annam photograph; it is not a recovered original product
photo or packaging image. Generated on 21 October 2026. No price or packaging
claims appear in the image. The original generated PNG remains in the workspace;
the bundled JPEG is encoded for web delivery.
