# Website image files

All uploaded food, category, banner and branding images use the media folder
configured by `PUBLIC_MEDIA_ROOT` (Django's `MEDIA_ROOT`). The database keeps
file paths and metadata. Existing editor images additionally keep a recovery
copy in the database and materialize a real file in `media/website/`.

| Folder | Content |
| --- | --- |
| menu/ | Dish and shop photos |
| categories/ | Category artwork |
| banners/ | Offer banners |
| brand/ | Website and bill logos |
| campaigns/ | Campaign artwork |
| imported/ | Configured images copied from static files or approved HTTPS sources |
| website/ | Legacy editor photos, served through the access-controlled image endpoint |

When serving media through a reverse proxy or bucket, block direct access to
`/media/website/*`. The included Caddy example does this; Django also rejects
these public paths. Use the existing `/platform/assets/...` endpoint so draft
and tenant access checks still run.

Run `python manage.py materialize_media --tenant annam --download` to copy
bundled images, materialize legacy editor images, and replace configured image
links with media paths after successful downloads. Startup runs the local
recovery before serving and imports remaining external configuration images
after the catalog seed/restore. Only the known Annam source hosts are permitted;
redirects, non-image payloads and oversized images are rejected. Failed imports
are reported and retain the original URL rather than replacing it with a
missing file. This command does not fetch CSS, fonts, payment scripts or normal
links. These are not image assets.

Existing owner replacements always take precedence over bundled recovery
files. Issued invoice data is not rewritten; the known historical static logo
path is resolved to the equivalent media logo during rendering.

Use Render's persistent disk configuration (`render.paid.yaml`) for permanent
uploads. The free configuration's `/tmp/media` folder is temporary. Imported
catalog and bundled files can be restored, but arbitrary newly uploaded dish,
category and banner photos require persistent storage and backups.

## Downloading a media backup

Store owners can use **Store settings → Download media ZIP**. The POST endpoint
is `/manage/settings/media-backup/`; it requires the store owner or a superuser,
CSRF protection and a noncached attachment response. Managers/staff cannot
export the image library. The archive contains store-referenced images from
products, categories, banners, configuration and the saved editor library,
including drafts. It includes inactive catalog photos but excludes unreferenced
files, other stores, invoices, WhatsApp attachments and environment secrets.

`backup-report.json` lists included files, missing/unreadable images and external
links not included. Inspect it before treating the ZIP as complete. The export
uses a temporary spool file, does not download remote URLs, does not modify
database records and does not leave the archive at a public URL. Bundled public
artwork and legacy database image bytes can supply files missing from disk.

When adding this feature to an existing ephemeral Render service, preserve the
current files first if possible: deploying the exporter itself can replace the
instance and erase uploads. Do not assume a code deployment is a backup.
