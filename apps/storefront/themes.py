"""Trusted theme and section registry. Tenant settings select options, never templates."""
THEMES = {"classic": {"name": "Kitchen Classic", "description": "Your current storefront, now customizable."}}
SECTIONS = (
    ("hero", "Welcome hero", "Headline, food photography and ordering links"),
    ("offers", "Offers & banners", "Active offers and promotional banners"),
    ("meals", "Daily menu", "Today's breakfast, lunch and dinner"),
    ("numbers", "Kitchen highlights", "Existing kitchen statistics"),
    ("categories", "Shop categories", "Browse your product collections"),
    ("showcase", "Food favourites", "Your configured food showcase tiles"),
    ("popular", "Popular products", "Popular shop products or featured dishes"),
    ("spotlight", "Product spotlight", "Your featured product and ingredients"),
    ("story", "How ordering works", "The steps from ordering to delivery"),
    ("closing", "Contact & visit", "Your closing contact and ordering section"),
)
SECTION_TEMPLATES = {key: f"storefront/sections/{key}.html" for key, _, _ in SECTIONS}
FONT_CHOICES = (("inherit", "Current brand fonts"), ("modern", "Modern · Figtree & Bricolage"),
                ("clean", "Clean · system sans serif"), ("editorial", "Editorial · serif headings"))
DENSITY_CHOICES = (("comfortable", "Comfortable"), ("compact", "Compact"), ("spacious", "Spacious"))
SHAPE_CHOICES = (("original", "Current rounded style"), ("soft", "Soft corners"), ("square", "Subtle corners"))
HERO_CHOICES = (("split", "Text beside food photography"), ("centered", "Centered introduction"))
MENU_CHOICES = (("columns", "Meal columns"), ("list", "Stacked meal cards"))
