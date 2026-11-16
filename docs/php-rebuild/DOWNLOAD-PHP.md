# Updated PHP downloads

These archives contain PHP application source from commit `d64c3db` on `php-rebuild`.

- [Download the entire PHP source ZIP](https://github.com/saran4125/annam_foods/raw/refs/heads/php-rebuild/docs/php-rebuild/annam-foods-php-source.zip)
- [Download the existing-site update ZIP](https://github.com/saran4125/annam_foods/raw/refs/heads/php-rebuild/docs/php-rebuild/annam-foods-php-ui-update.zip)

The source ZIP contains the complete tracked `php-app` code, tests, deployment
scripts and documentation. It does not contain a database, private configuration,
installation credentials or uploaded media.

For an existing PHP site, use the update ZIP. Follow `UPDATE-EXISTING-SITE.txt`
inside it: merge the private code and public assets, keep the existing database,
configuration and media, then restart PHP / clear OPcache and refresh the browser.

SHA-256 checksums are in `PHP-ZIPS-SHA256.txt`.
