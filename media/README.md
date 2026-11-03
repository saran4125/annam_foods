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

## Original public image recovery

Only original public storefront images belong in `catalog/`, `categories/` and
`brand/`. These directories are allowed in Git. `website/` and other private upload
folders remain ignored and must never be committed with customer/invoice material.

`php-app/resources/public-media.json` inventories the URLs from the saved source
catalog. A file is recovered only when a real image downloads successfully and its
original bytes pass type/size validation and SHA-256 verification. Failed requests
remain explicitly unavailable; they must not become broken product image paths.

Run `php php-app/bin/download-public-media.php` from an environment that can reach
Annam's public image CDN. It resumes verified cached files. Then run the local
SQLite image assignment command (with the private database settings configured):
`php php-app/bin/apply-public-media.php --apply`. New release preparation applies
the same verified mapping automatically. Existing owner-uploaded images and other
stores are preserved. Rebuild the local ZIP after recovery to include the media.

The current environment blocks the source hosts with proxy 403 / direct DNS
failure. The available supplied original logos are tracked under `brand/`; source
product-photo recovery is not claimed until verified image files are present.
