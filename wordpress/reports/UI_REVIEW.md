# Storefront UI review · 28 September 2026

Reviewed the running Annam storefront at 1280px desktop, 768px tablet and
390px phone widths. The same theme serves every kitchen; the demo site's
separate branding and content remain intact.

| Page type | Finding | Change |
|---|---|---|
| Home | The image-led layout fit desktop and phone widths; default block and WooCommerce text sizes diverged | Applied a shared 16px body scale, 30–40px page titles, consistent product card type and 44px control targets |
| Shop | WooCommerce's fresh-install “coming soon” setting hid the public catalog; shop cards differed from collection and search cards | Disabled the catalog-only gate during provisioning and switched shop to the same archive renderer |
| Collections | Collection cards were photographed, but their titles, prices and buttons differed from homepage cards | Unified title, price, button size, radius and minimum height |
| Search | The phone search field expanded to almost zero width | Opened it as a full-width field below the header; site search now queries products even without a `post_type` parameter |
| Product | The mobile gallery had a 56px gap before the title; imported images exposed source filenames as descriptions | Removed the extra gallery margin and replaced untouched filename descriptions with product names |
| Cart | WooCommerce default notices and form controls looked unrelated to the storefront | Applied the store's type, color and minimum control height |
| Daily meals | The page title was an H2 while other listing pages used H1 | Standard pages now render an H1; the unconfigured meal message remains explicit |
| Account | The desktop sign-in form was overly wide; inputs were too small on phones | Constrained the account content and set 16px mobile inputs |
| Navigation/footer | Phone icon targets were small, and the menu overlay ignored the store palette | Increased targets to 44px and styled the menu with the shared cream/dark palette |

The review includes desktop and phone overflow checks, tablet navigation,
mobile drawer opening, search submission, product gallery, filled cart, and
the account form. Product and category photos use the source imagery; 290
untouched product image descriptions, 34 category image descriptions and the
logo description were improved
without replacing owner-written descriptions. Draft policy/campaign pages and
the disabled checkout are outside the public shopping flow until their content
and business rules are approved.

Button follow-up: photographed product cards now have full-width, aligned
50px actions. Available items use a darker terracotta fill with cream text;
unavailable items use a separate “Sold out” badge and a restrained “View
product” action. The product-page add button fills the space beside quantity
on phones, while pincode checking stays visually secondary. The same action
styles apply to the home, shop, collection, and search listings.
