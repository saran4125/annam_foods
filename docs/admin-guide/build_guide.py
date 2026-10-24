"""Build the simple staff reference: exactly one page and screenshot per tab."""
from pathlib import Path
import json
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent
TABS = [
    ('Dashboard', 'dashboard', 'See today’s menu and a quick overview of your products.', [
        ('Counts', 'Products on sale, hidden products, shop items and categories.'),
        ('Today’s menu', 'The dishes listed for breakfast, lunch and dinner.'),
        ('Choose dishes', 'Opens the screen for selecting a day’s menu.'),
        ('Shortcuts', 'Quick links for adding dishes, offers and delivery areas.'),
    ]),
    ('Orders & billing', 'orders', 'Find orders, check their progress and open bills.', [
        ('Create booking', 'Enter a phone, counter or WhatsApp order.'),
        ('Order number', 'Opens the customer, address, items and payment details.'),
        ('Status / Payment', 'Delivery progress and payment received are shown separately.'),
        ('Bills', 'Open a paid order to view, print or save its bill.'),
    ]),
    ('WhatsApp inbox', 'whatsapp', 'Read customer messages and reply to conversations.', [
        ('Conversation list', 'Choose the customer you want to speak with.'),
        ('Messages', 'Read the customer’s request and the kitchen’s replies.'),
        ('Reply', 'Type a response; normal replies need a customer message within 24 hours.'),
        ('Create booking', 'Turn the customer’s request into an order.'),
    ]),
    ('Dishes & products', 'products', 'Manage the items you sell and their prices.', [
        ('Meals / Other items', 'Cooked meals and packed shop products.'),
        ('Add dish', 'Create a new item with its name, price and photo.'),
        ('Edit', 'Change an existing item’s details.'),
        ('On sale', 'Show or hide the product across all dates.'),
    ]),
    ('Daily menus', 'daily-menus', 'Choose which dishes are available for each meal and date.', [
        ('Meal', 'Select breakfast, lunch or dinner.'),
        ('Date', 'Choose Today, Tomorrow or a date from the calendar.'),
        ('Dish toggles', 'Turn on the dishes you want to serve that day.'),
        ('Save menu', 'Saves only the selected date and meal.'),
    ]),
    ('Categories', 'categories', 'Group similar products so they are easier to find.', [
        ('Category', 'A group such as Podi, Pickles or Sweets.'),
        ('Add record', 'Create a new category.'),
        ('Edit', 'Change the category name, description or photo.'),
        ('Show category', 'Show or hide the group on the website.'),
    ]),
    ('Meal times', 'meal-times', 'Control when customers can order each meal.', [
        ('Meal', 'Breakfast, lunch or dinner.'),
        ('Edit', 'Opens the ordering cutoff and delivery-time fields.'),
        ('Orders close', 'The last time customers can place that meal order.'),
        ('Available', 'Enable or pause the meal time.'),
    ]),
    ('Delivery areas', 'delivery-areas', 'Manage the places where meals can be delivered.', [
        ('Pincode', 'The exact delivery pincode for that area.'),
        ('Fee', 'The delivery charge added to the order.'),
        ('Minimum', 'Required food value before the delivery fee.'),
        ('Delivering', 'Turn the area on or off; use Edit to change its details.'),
    ]),
    ('Offer banners', 'offer-banners', 'Show promotional pictures and messages on the home page.', [
        ('Banner', 'An offer picture with a heading, message and optional link.'),
        ('Add record', 'Create a new promotional banner.'),
        ('Edit', 'Change the offer text, picture or link.'),
        ('Show banner', 'Show or hide the promotion.'),
    ]),
    ('Website pages', 'website-pages', 'Manage About us, policies and other information pages.', [
        ('Pages', 'The information customers can read on your website.'),
        ('Add record', 'Create a new information page.'),
        ('Edit', 'Change the title and page content.'),
        ('Published', 'Controls whether customers can open the page.'),
    ]),
    ('Store settings', 'store-settings', 'Update the basic details customers see about your business.', [
        ('Contact details', 'Store name, phone, email and public address.'),
        ('Branding', 'Your website logo and brand colour.'),
        ('Announcements', 'Short messages shown on the website.'),
        ('Save settings', 'Applies the details you have changed.'),
    ]),
]

D = Document()
section = D.sections[0]
section.orientation = WD_ORIENT.LANDSCAPE
section.page_width, section.page_height = Cm(29.7), Cm(21)
section.top_margin, section.bottom_margin = Cm(1.25), Cm(1.2)
section.left_margin, section.right_margin = Cm(1.65), Cm(1.65)
section.header_distance = section.footer_distance = Cm(.5)
normal = D.styles['Normal']
normal.font.name = 'Arial'
normal.font.size = Pt(11)
normal.font.color.rgb = RGBColor.from_string('302A25')
normal.paragraph_format.line_spacing = 1.1
normal.paragraph_format.space_after = Pt(7)
heading = D.styles['Heading 1']
heading.font.name, heading.font.size = 'Arial', Pt(26)
heading.font.color.rgb = RGBColor.from_string('241C16')
heading.paragraph_format.space_after = Pt(5)
D.core_properties.title = 'Annam Foods — Staff Quick Guide'
D.core_properties.subject = 'One page per everyday admin tab'
D.core_properties.author = 'Annam Foods'
D.core_properties.keywords = 'Annam Foods, staff, quick guide'

header = section.header.paragraphs[0]
r = header.add_run('ANNAM FOODS  /  STAFF QUICK GUIDE')
r.font.size = Pt(8)
r.font.color.rgb = RGBColor.from_string('8A7668')
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = footer.add_run('Annam Foods  ·  ')
r.font.size = Pt(8)
r.font.color.rgb = RGBColor.from_string('8A7668')
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)
footer.add_run(' / '+str(len(TABS))).font.size = Pt(8)

for index, (title, key, purpose, labels) in enumerate(TABS):
    if index:
        D.add_page_break()
    D.add_heading(title, level=1)
    p = D.add_paragraph(purpose)
    p.paragraph_format.space_after = Pt(10)
    p.runs[0].font.color.rgb = RGBColor.from_string('6C5E52')
    image = D.add_paragraph()
    image.paragraph_format.space_after = Pt(12)
    picture = image.add_run().add_picture(str(ROOT/'screenshots'/(key+'.png')), width=Cm(26.2))
    picture._inline.docPr.set('descr', 'Real admin screen: '+title)
    for label, meaning in labels:
        p = D.add_paragraph()
        r = p.add_run(label+'  —  ')
        r.bold = True
        r.font.color.rgb = RGBColor.from_string('A94D00')
        p.add_run(meaning)
        p.paragraph_format.widow_control = True

D.save(ROOT/'Annam-Foods-Admin-Guide.docx')
(ROOT/'guide-index.json').write_text(json.dumps([
    {'title':title, 'screenshot':key, 'page':index+1}
    for index,(title,key,*_) in enumerate(TABS)
], indent=2)+'\n')
print('Created the 11-page staff guide: one tab, one screenshot and four short explanations per page.')
