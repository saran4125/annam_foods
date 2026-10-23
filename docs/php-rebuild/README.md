# PHP rebuild checkpoint

This is the first independently running PHP review build. It is on branch
`php-rebuild`; the current Django/Render website and live Supabase data are not
replaced. Review code is in [`php-app`](../../php-app/README.md).

- [Download PHP review ZIP](annam-php-preview.zip)
- [Delivery-area screenshot](admin-zones.png)
- [Cart and delivery check screenshot](cart-delivery.png)

The ZIP contains source, design assets, a bundled recovery logo and private
configuration instructions. It excludes actual environment settings, passwords,
database exports, uploaded media, browser sessions and logs. Restore your saved
media folder and a **test copy** of the database before running it.

| Area | PHP checkpoint |
| --- | --- |
| Admin login and store membership | Implemented, including existing PBKDF2 password verification |
| Products, categories, photos, banners and pages | Basic management implemented |
| Dated menus / Today / Tomorrow | Implemented, with revision and stock-counter protection |
| Delivery zones, meal coverage, fees, minimums | Implemented |
| Home, menu, shop, item and cart pages | Implemented for review; full visual/content parity remains |
| Guest checkout / order creation | Not migrated yet; checkout visibly disabled |
| Razorpay / refunds / billing | Not migrated yet; no payment collection |
| WhatsApp / n8n / outbound jobs | Not migrated yet |
| Hostinger compatibility | Requires pdo_pgsql and a verified Supabase TLS connection |

Verification: 14 native PHP behavioural tests, browser flows for login, menu
saving, product creation, delivery validation and mobile navigation, plus HTTP
checks for CSRF and private files. The existing 546 Django tests also pass.
Provider integrations, production deployment and feature parity are not certified
by this checkpoint.
