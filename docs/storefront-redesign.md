# Storefront redesign

> Historical implementation note. The status and test count below describe an
> earlier redesign, not the complete store requested in September 2026. For the
> current image-only hero, owner-editable CMS, and remaining implementation work,
> use [OPENCODE_STOREFRONT_HANDOFF.md](OPENCODE_STOREFRONT_HANDOFF.md). Its storefront
> requirements supersede conflicting visual guidance here; AGENTS.md still
> governs architecture and tenant isolation.

Status: **implemented.** 110 tests green.

Built with no photography available (Annam has zero dish images), so the design
is carried by typography and the meal-slot structure, with a tinted initial
tile standing in wherever a photo will eventually go. When real photos arrive
the same layout takes them with no further work.

## Goal

**Take the UI/UX from sweetkaramcoffee.in. Take the kitchen model from Annam.**

Sweet Karam is the reference for how the storefront should *look and feel* — a
clean, airy, neutral palette, strong typography, food photography carrying the
page. Annam is the reference for how a cloud kitchen actually *works* — meal
slots with cutoffs, a menu that changes daily, pincode-gated delivery.

Keep our slot-based ordering flow and all 110 tests green.

## What to borrow, and what not to

The two businesses sell differently, and copying the wrong half produces a
storefront that fights the product.

Sweet Karam is a **packaged-goods store**: courier-shipped, browse any time,
pack sizes, discounts. Annam is **daily meals**: order by 11am for today's
lunch, delivered in a window, to a serviceable pincode only.

**Borrow — presentation:**

- Neutral near-white ground that lets food photography dominate
- Product cards with real imagery, generous padding, clear price
- Slim sticky header, logo left, cart right with a count bubble
- Seasonal/festive banners (Annam already runs Krishna Jeyanthi offers)
- Clean type hierarchy and restrained use of the brand colour
- Responsive grid that collapses cleanly on a phone — most orders are mobile

**Do not borrow — commerce model:**

| Pattern | Why it doesn't fit |
|---|---|
| Pack-size dropdowns | A meal is one portion |
| Strike-through "was ₹X" pricing | Daily meals aren't discounted that way |
| Star ratings and review counts | There is no review system. Inventing them would be dishonest |
| "Limited drop" urgency badges | The real urgency is the slot cutoff, which we already show |
| Gift hampers, corporate gifting | Not a cloud kitchen's business |
| International shipping | Delivery is pincode-bound by design |

The genuine scarcity signal here is **the cutoff clock**, not manufactured
urgency. Lean on it: "ordering closes at 11:00" is true and useful.

## What Annam's model requires that a packaged store doesn't

These must survive the restyle, because they *are* the product:

- Date tabs (today / tomorrow) and slot tabs, with closed slots visibly closed
- The cutoff banner explaining why a slot can't be ordered from
- Pincode entry before checkout, with area choice when a pincode has several
- Minimum-order state on the cart
- The kitchen's own phone number, prominent — customers do ring

## Grounding constraints (checked against the code)

- `MenuItem.image` and `Banner.image` exist → imagery is feasible with zero
  model changes.
- `:root` currently exposes only `--brand`, `--brand-dark`, `--accent` (from
  `TenantConfig.theme`). The neutrals (`--ink`/`--paper`/`--card`) are
  hardcoded in CSS; promote them to variables so each kitchen can tune them →
  fits the "customisation is configuration" rule.
- `Cart.count` is in the template already → sticky header badge is trivial.
- Tests now assert **stable hooks**, not copy. Five assertions that read UI
  prose (`Minimum order not met`, `Your cart is empty`, `closed at`, and the
  fragile two-character `isn` / `don` substrings) were moved onto
  `data-testid` attributes, so the restyle is free to reword every visible
  string. **Keep these attributes and the `btn-add` class:**

  | Hook | On |
  |---|---|
  | `data-testid="orders-paused"` | the suspended-kitchen strip in base.html |
  | `data-testid="flash"` | message flashes |
  | `data-testid="slot-closed"` | the cutoff banner in menu.html |
  | `data-testid="cart-empty"` | the empty-cart state |
  | `data-testid="checkout"` + `data-blocked="…"` | the checkout button; reason is `pincode`, `minimum`, `closed` or `paused` |
  | `class="btn-add"` | add-to-cart button |

  What tests still assert directly — dish names, prices, totals, the brand
  name, the zone name — is behaviour, and should stay asserted.
- No theme key for a hero image surfaced to templates yet → handled via the
  existing `Banner.image` (the first active banner becomes the hero image if
  present; falls back to a clean typographic hero when absent — no migration
  needed).

## What changes by file

### 1. `static/css/storefront.css` (full restyle)

- **Palette**: promote `--paper`/`--card`/`--ink` neutrals to themable
  variables; shift from warm `#FCFAF7` to a neutral near-white; keep `--brand`
  for buttons/accents.
- **Typography**: tighter display face for headings (system-ui stack, larger
  `h1`, cooler tracking), refined `font-weight` hierarchy; body stays clean
  sans.
- **Header**: slim white sticky bar (border-bottom, subtle shadow on scroll),
  logo-left / nav-right pattern like Sweetkaram, cart as an outlined
  icon-button with a `--brand` count bubble.
- **Hero**: full-width, large, optional background image (first active Banner),
  overlay + brand name/tagline + primary CTA; when no image, a brand-tinted
  gradient panel. Value-strip beneath.
- **Slot cards**: flat white cards, generous padding, larger dish names, image
  thumbnails (from `MenuItem.image`) where present, price styled as the CTA
  anchor, `pill` status preserved.
- **Menu/dishes**: card rows with an image column + content + `btn-add`; tabs
  styled as a pill bar (unchanged logic, glued to the new look).
- **Cart**: keep layout, soften to a single bordered card for lines, keep
  totals/minimum/zone logic untouched, accent only the final "Checkout"
  primary.
- **Footer**: neutral, top-border, three columns (brand + phone, quick pages,
  tagline).

### 2. `templates/base.html`

- Sticky header wrapper + cart badge markup (`b` already exists).
- **The hero belongs in `home.html`, not here.** Only `home()` puts `banners`
  in the context — cart, menu and page views do not — so a hero block in the
  base template renders empty on every page but one.
- Keep the `data-testid` hooks listed above and the `btn-add` class.

### 3. `templates/storefront/home.html`

- Hero section (uses `banners.0.image` if present) + value strip.
- Slot cards upgraded (image + price emphasis), same `highlights` context.
- Preserve `Annam Foods`, dish-name, price, and shut-pill strings.

### 4. `templates/storefront/menu.html`, `cart.html`, `page.html`

- Visual-only refinements; **no data/model/view changes**; all existing classes
  (`btn-add`, `tabs`, `totals`, `strip`, `prose`) retained so no test breaks.

### 5. (Optional, no migration) hero image key

- No view changes needed for the core look. Future-proof note: a per-kitchen
  hero image would be a new `TenantConfig.theme` key + one template line —
  deferred until asked.

## One thing that will disappoint without content

The Sweet Karam look is carried by photography. Annam currently has **zero
menu images** — `MenuItem.image` exists and is empty for all nine seeded
dishes. A photo-led design over empty image slots looks worse than the current
text-led one.

So either commission or collect dish photos before implementing, or design the
no-image state deliberately: a warm tinted tile with the dish initial, sized
the same as a photo, so a kitchen with no pictures still looks composed. The
second is the safer default, since every new client starts with no photos.

## Verification

After implementing: `uv run pytest` (expect 110 green), `manage.py check`, and
a local smoke via curl on `127.0.0.1:8000`. Then look at it on a phone-width
viewport — that is where most orders come from, and where a desktop-first
restyle usually falls apart.
