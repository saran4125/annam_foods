# Updated PHP downloads

The source and update archives include the 17 November payment, private invoice PDF, receipt refresh and layout fixes on `php-rebuild`. The separate reviewed database archive is unchanged. See [update instructions](PAYMENT-RECEIPT-UPDATE.md).

- [Download the entire PHP source ZIP](https://github.com/saran4125/annam_foods/raw/refs/heads/php-rebuild/docs/php-rebuild/annam-foods-php-source.zip)
- [Download the existing-site update ZIP](https://github.com/saran4125/annam_foods/raw/refs/heads/php-rebuild/docs/php-rebuild/annam-foods-php-ui-update.zip)

The source ZIP contains the complete tracked `php-app` code, tests, deployment
scripts and documentation. It does not contain a database, private configuration,
installation credentials or uploaded media.

For an existing PHP site, use the update ZIP. Follow `UPDATE-EXISTING-SITE.txt`
inside it: merge the private code and public assets, keep the existing database,
configuration and media, then restart PHP / clear OPcache and refresh the browser.

SHA-256 checksums are in `PHP-ZIPS-SHA256.txt`.

## Reviewed fresh-install database

[Download the reviewed PHP database ZIP](https://github.com/saran4125/annam_foods/raw/refs/heads/php-rebuild/docs/php-rebuild/annam-foods-php-reviewed-database.zip).

Contains 325 catalog products, 64 approved delivery areas and the reviewed
breakfast starting menu. Read `READ-DATABASE-FIRST.md` inside the archive.
This is a reviewed public snapshot plus Python manifests, **not a full live Render
export**. It contains no existing accounts/orders, uploaded media or provider keys.
Use it only for a fresh installation. Keep an existing site's database and private
configuration. `REVIEWED-DATABASE-REPORT.json` documents what was verified and the
remaining live-data comparison limits.
