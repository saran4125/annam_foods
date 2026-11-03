# Annam image comparison — 3 November 2026

Compared 425 public annamfood.in pages and their image metadata with the Annam
catalog. Original source files are checksum-verified and stored in `media/`.
Reviewed spelling differences match Diwali Mega Combo Pck, Assorted Assorted
500gm, Diwal Moru Moru Murukku, Tapiaco Chips and Mini Milagu Apapalm to their
existing store products. No product prices, schedules or historical orders changed.

- Every Diwali product photo, its three category images and promotional banner
  have a verified local file.
- 318 of 324 catalog products and all 38 categories have local images.
- PHP: 80 public pages and 208 displayed image URLs checked; no failed requests.
- Live Django: 28 public pages and 214 displayed images verified; no failed
  requests. The deployed Diwali fix was visible during the check.
- Existing legacy image filenames and the old logo URL have recovery copies in
  Git, so they can be restored after redeployment.

Six added meal products have no confidently matching original in the current
source catalog: Spl Bisibelabath, Chow Chow Kootu, Morekuzhambu, Kose Poriyal,
Kancheepuram Idly (2), and Onion Chennai Masala. They retain an empty image field;
no different dish was substituted. Original photos or an exact source product
link are needed to finish these six.

Evidence: `php-image-audit.json`, `php-rendered-image-audit.json`,
`live-image-audit.json`, and `media-recovery-report.json`. Browser verification
pages were rejected as product-image evidence; public sitemap and hydrated
page metadata provided the successful source comparison.
