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

# Plain-text fields the visual editor may change. Products/prices remain catalog data.
# key -> (friendly label, maximum length, default copy)
COPY_FIELDS = {
    'brand.name': ('Website name', 120, ''),
    'hero.kicker': ('Small heading', 100, 'Home-made, every day'),
    'hero.title': ('Main headline', 160, 'Home-made food, cooked fresh for your table.'),
    'hero.body': ('Introduction', 600, 'Breakfast, lunch and dinner cooked to your slot — plus podis, pakshanams, sweets and pickles made in small batches and shipped fresh.'),
    'hero.cta': ('Order button', 60, 'Order today’s meals'),
    'hero.shop_cta': ('Shop button', 60, 'Shop the pantry'),
    'hero.proof': ('Food promise', 80, 'Pure vegetarian'),
    'offers.title': ('Offer headline', 160, ''),
    'offers.body': ('Offer description', 600, ''),
    'offers.kicker': ('Offer label', 80, 'Festival special'),
    'offers.cta': ('Offer button', 60, 'See the offer'),
    'meals.kicker': ('Small heading', 80, 'Daily food menu'),
    'meals.title': ('Heading', 160, 'From today’s kitchen'),
    'meals.body': ('Description', 400, 'Order before the cutoff and we cook it for your slot.'),
    'categories.kicker': ('Small heading', 80, 'Shop by category'),
    'categories.title': ('Heading', 160, 'Made in our kitchen'),
    'showcase.kicker': ('Small heading', 80, 'Explore the kitchen'),
    'showcase.title': ('Heading', 160, 'Food favourites'),
    'popular.kicker': ('Small heading', 80, 'Loved by everyone'),
    'popular.title': ('Heading', 160, 'Popular in the shop'),
    'popular.body': ('Description', 400, 'The podis, pakshanams and sweets our regulars reorder.'),
    'spotlight.kicker': ('Small heading', 100, 'From our kitchen'),
    'spotlight.title': ('Product headline', 160, ''),
    'spotlight.body': ('Product story', 1000, ''),
    'spotlight.points': ('Ingredients or highlights (one per line)', 1200, ''),
    'spotlight.cta': ('Button text', 60, 'Order now'),
    'story.kicker': ('Small heading', 80, 'Why order direct'),
    'story.title': ('Heading', 160, 'A shorter journey from the stove to your table.'),
    'story.body': ('Your story', 1000, 'You choose the meal and delivery slot. The kitchen sees the same live menu, prepares against confirmed demand, and sends it straight to your area.'),
    'story.cta': ('Button text', 60, 'Build your order'),
    'story.step1_title': ('First step', 60, 'Choose'),
    'story.step1_body': ('First step description', 300, 'Pick today or tomorrow and a meal slot.'),
    'story.step2_title': ('Second step', 60, 'Check'),
    'story.step2_body': ('Second step description', 300, 'Confirm delivery availability with your pincode.'),
    'story.step3_title': ('Third step', 60, 'Enjoy'),
    'story.step3_body': ('Third step description', 300, 'We cook for the slot and deliver it fresh.'),
    'closing.kicker': ('Small heading', 80, 'Ready when you are'),
    'closing.title': ('Heading', 160, 'Good food is one tap away.'),
    'closing.body': ('Closing message', 600, 'Choose today’s meal or fill a pantry box. We confirm your area, cook it fresh, and bring it to your door.'),
    'closing.cta': ('Order button', 60, 'Order today’s meals'),
}
IMAGE_FIELDS = {'hero': 'Welcome photo', 'offers': 'Offer photo', 'spotlight': 'Product spotlight photo', 'logo': 'Store logo'}
