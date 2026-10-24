from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image
import json

ROOT=Path(__file__).resolve().parent
# One task per page. Button names follow the actual PHP screens.
TOPICS=[('Start here',
  '36-navigation',
  'Get comfortable with the admin panel',
  ['Use the menu on the left to open a tab. The page heading tells you where you are.',
   'A green toggle means On. A grey toggle means Off. Click the toggle to change it.',
   'On an edit form, finish with Save changes or the page’s Save button. A success message confirms the '
   'save.',
   'Use View website to check the menu, products and saved content changes.'],
  'Some financial actions are available only to the store owner. Screenshots show practice records; your '
  'names, prices, dates and counts may differ.'),
 ('Dashboard',
  '02-dashboard',
  'Left menu → Dashboard',
  ['Check the totals for dishes on sale, hidden dishes, shop items and categories.',
   'Read Today’s menu to see the dishes listed for each meal and the order cutoffs.',
   'Click Choose dishes to open the Daily menus screen.',
   'Use the shortcuts to add a dish, create an offer banner or check delivery areas.'],
  'The dashboard is an overview. Use Orders & billing to see and manage actual orders.'),
 ('Orders & billing',
  '13-orders',
  'Left menu → Orders & billing',
  ['Use Search to find an order by order number, customer name or mobile number.',
   'Choose a channel to see website, manual or WhatsApp bookings.',
   'Check the Total, Status and Payment columns.',
   'Click an order number to open its details. To enter a phone or counter booking, click + Create booking.'],
  'Order status and payment status mean different things: an order can be confirmed while its payment is '
  'still pending.'),
 ('Create a manual or WhatsApp booking',
  '14-booking',
  'Orders & billing → + Create booking',
  ['Enter the customer’s name and mobile number.',
   'Choose Manual booking or WhatsApp booking to record where the order came from.',
   'Choose Manual payment or Cash on delivery. The new booking starts unpaid.',
   'Select a delivery area and enter the full address. Choose Collection at kitchen only for a pickup '
   'order.'],
  'The selected delivery area supplies its delivery fee and minimum food value. Do not use Collection for a '
  'delivery order.'),
 ('Choose items for a booking',
  '15-booking-items',
  'Create booking → scroll to Choose items',
  ['Type a dish or product name in Search dishes & products.',
   'Enter the quantity next to each required item. Leave other quantities blank or at zero.',
   'Review the customer, address, items and quantities.',
   'Click Create unpaid booking. Open the new order to review its total and arrange payment.'],
  'Prices come from the current catalog. Enter a quantity, not a price. A booking does not automatically '
  'mean payment was received.'),
 ('Confirm an offline payment',
  '16-order-detail',
  'Orders & billing → open an unpaid manual/COD order → scroll to Payment reference',
  ['Check the order number, customer and total against the payment you received.',
   'For an offline payment, enter the Payment reference, such as a cash note or bank/UPI reference.',
   'Switch on I confirm the payment was received, then click Confirm payment.',
   'Check that the payment now says paid. If a bill is available, open View / print bill.'],
  'Confirm only after receiving the money. Online payments must be verified through their payment-check '
  'action, not manually marked paid. Ask the owner if you need access.'),
 ('Prepare, dispatch and deliver',
  '17-order-actions',
  'Open an order → Next step',
  ['Choose the next status: confirmed → preparing → out for delivery → delivered.',
   'Add a note if needed. Enter rider name and phone when sending the delivery out.',
   'Click Update order after choosing the correct next step.',
   'To cancel an eligible order, choose cancelled, enter the reason and click Update order.'],
  'A cancelled order and a refunded payment are separate actions. Cancelling does not automatically refund '
  'money. The order history records status changes.'),
 ('Open and print a bill',
  '18-bill',
  'Paid order → View / print bill',
  ['Check the logo, bill number, customer details, delivery address and items.',
   'Check the total and payment reference. For an eligible paid order without a bill, the owner can use '
   'Issue bill.',
   'Click Print / Save PDF at the bottom of the bill. Choose your printer or Save as PDF in the browser.',
   'Use A4 and check the print preview before printing or saving.'],
  'An issued bill keeps its original details. Later price or content changes do not rewrite it. Ask the '
  'owner if a paid order is missing its bill.'),
 ('WhatsApp inbox',
  '19-inbox',
  'Left menu → WhatsApp inbox',
  ['Choose the customer conversation on the left.',
   'Read the customer’s messages and the kitchen’s replies in the conversation.',
   'Use Mark as read after reviewing the conversation.',
   'If the customer wants to order, click Create booking and check the details with them.'],
  'Messages appearing in the inbox do not automatically create an order or a bill. Staff must create the '
  'booking.'),
 ('Reply to a WhatsApp customer',
  '21-reply-compose',
  'WhatsApp inbox → select a conversation',
  ['Type your message in Reply. Keep it clear and include any details you need the customer to confirm.',
   'Click Queue reply. The system sends the queued message through the configured provider.',
   'Check the message status: pending means waiting; sent, delivered and read show its progress.',
   'Use View attachment to open a received attachment when one is available.'],
  'Normal replies are available for 24 hours after the customer’s last message. If the window is closed, ask '
  'the customer to send a new message.'),
 ('Dishes & products: meals',
  '03-meals',
  'Left menu → Dishes & products → Meals',
  ['Choose Meals to work with breakfast, lunch and dinner dishes.',
   'Use the meal buttons or Search to narrow the list. Not assigned shows dishes that have not been linked '
   'to a meal schedule.',
   'Click Edit to change a dish’s name, price, description or photo.',
   'Use Daily menus to choose which dishes appear for a specific date and meal.'],
  'Switching a product off in this list hides it across dates. To remove it only from tomorrow’s lunch, '
  'change tomorrow’s lunch in Daily menus.'),
 ('Dishes & products: other items',
  '04-shop',
  'Dishes & products → Other items',
  ['Choose Other items for packed shop products such as podi, sweets, pickles and health products.',
   'Use Search to find a product, then click Edit.',
   'Change its price, description, category or photo as needed.',
   'Use its On sale toggle to show or hide it. Click + Add dish to create another product and choose Other '
   'items as its Type.'],
  'Other items are packed shop products. They are not selected in the breakfast, lunch or dinner menu.'),
 ('Add or edit a dish/product',
  '05-dish-form',
  'Dishes & products → + Add dish or Edit',
  ['Enter the Name and choose the Type: Meals or Other items.',
   'Choose a Category and enter the selling Price in rupees.',
   'Add a short Description. Check the Vegetarian and On sale toggles. Use Display order to control sorting.',
   'Scroll down to add a photo if needed, then click Save changes.'],
  'A new meal dish must also be selected in Daily menus before it appears for that date and meal. Creating '
  'the product alone does not choose its menu date.'),
 ('Add a photo and feature a product',
  '06-dish-photo',
  'Dish/product form → scroll to Photo',
  ['Click the file chooser under Photo and select a JPG, PNG or WebP image.',
   'Use a clear food photo smaller than 3 MB. Leave the field blank to keep the existing photo.',
   'For a product you want highlighted on the home page, turn on Feature in popular products.',
   'Click Save changes and open View website to check the result.'],
  'Popular product placement also depends on the shop being enabled. The image chooser changes this '
  'product’s photo; it does not change every image on the website.'),
 ('Daily menus',
  '07-daily-menu',
  'Left menu → Daily menus',
  ['Choose Breakfast, Lunch or Dinner.',
   'Click Today or Tomorrow, or choose Menu date and click View menu. Check the displayed date and meal.',
   'Turn on the dishes you want for that date. Turn off dishes you do not want for that date.',
   'Click Save [meal] menu, then check the success message and View website → Daily menu.'],
  'Saving changes only the selected meal/date. Saving with every dish off makes that date’s menu empty. An '
  'old category name such as Tuesday Breakfast is just a label; check the selected date here.'),
 ('Categories',
  '08-categories',
  'Left menu → Categories',
  ['Use this tab to group products, for example Podi, Pickles or Sweets.',
   'Click + Add record to create a category, or Edit beside an existing category.',
   'Enter its Name and URL name. For the URL name, use lowercase words with hyphens, such as '
   'health-products.',
   'Add a description/photo if needed, check Show category, and click Save changes. Assign products to it in '
   'their edit forms.'],
  'Changing a category’s URL name changes its shop link. Keep an existing URL name unless there is a reason '
  'to change it.'),
 ('Meal times',
  '09-meal-times',
  'Left menu → Meal times',
  ['Find Breakfast, Lunch or Dinner and click Edit.',
   'Check the meal name and the ordering cutoff.',
   'Use the Available toggle to enable or disable a meal time.',
   'Use the edit screen to change the cutoff or delivery window, then save.'],
  'The cutoff controls when customers can stop placing orders for that meal. This is different from the time '
  'the food will be delivered.'),
 ('Change a meal cutoff',
  '10-cutoff',
  'Meal times → Edit',
  ['Keep the existing Meal key for an existing meal, such as breakfast, lunch or dinner.',
   'Set Orders close to the last time an order can be placed.',
   'Set Delivery starts and Delivery ends if you use a delivery window.',
   'Check Available and click Save changes.'],
  'Times use the kitchen’s configured local time. A 06:30 cutoff means 6:30 AM. Changing a cutoff affects '
  'new meal ordering.'),
 ('Delivery areas',
  '11-zones',
  'Left menu → Delivery areas',
  ['Search by area name or pincode.',
   'Check each row’s Pincode, Fee and Minimum food value.',
   'Use the Delivering toggle to enable or pause a meal delivery area.',
   'Click Edit to change its details, or + Add record to add another approved area.'],
  'Minimum means the food value before delivery fee. Example: with a ₹100 minimum and ₹30 fee, ₹100 of food '
  'qualifies and the total before any extra tax is ₹130.'),
 ('Add or change a meal delivery area',
  '12-zone-form',
  'Delivery areas → + Add record or Edit',
  ['Enter the Area name and exact six-digit Pincode.',
   'Enter the Delivery charge and Minimum food value in rupees.',
   'Select each meal this area serves: Breakfast, Lunch, Dinner and/or Snacks.',
   'Check Delivering and click Save changes. If one pincode has multiple areas, keep each area’s correct fee '
   'and minimum.'],
  'Customers outside active meal coverage cannot place that meal order. Check the correct area, pincode, '
  'delivery fee and minimum food value.'),
 ('Offer banners',
  '29-banners',
  'Left menu → Offer banners',
  ['Find the offer you want to change and click Edit.',
   'Use the active/show toggle to show or hide the banner.',
   'Click + Add record to create a new promotion.',
   'After saving, open View website and check the offer section.'],
  'A banner is a promotional picture and message. It does not automatically reduce product prices or create '
  'a discount.'),
 ('Create an offer banner',
  '30-banner-form',
  'Offer banners → + Add record',
  ['Enter a clear Heading and a short Message.',
   'Enter the Button link customers should open when they click the offer, such as /shop/ or a full HTTPS '
   'link.',
   'Choose a promotional Photo, set the display order and keep the offer active when ready.',
   'Click Save changes and check the banner on the website.'],
  'Use an image for a visible offer. Showing a banner does not schedule an automatic end date; hide it when '
  'the offer ends.'),
 ('Website pages',
  '31-pages',
  'Left menu → Website pages',
  ['Find a page such as About us, Privacy policy or Refund policy.',
   'Click Edit to change it, or + Add record to create a new page.',
   'Use the Published/show toggle to make it available or hide it.',
   'After saving, open the matching page on the customer website and read it once.'],
  'A hidden page is not available to customers. Check policy wording with the owner before publishing '
  'changes.'),
 ('Write or edit page content',
  '32-page-form',
  'Website pages → + Add record or Edit',
  ['Enter the page Title and its URL name, such as refund-policy.',
   'Type the content in the body field. Use # Heading for a heading, **bold** for bold text, and - at the '
   'start of a line for a list.',
   'Add a Search description if needed and turn on Publish page when ready.',
   'Click Save changes. Open /p/your-url-name/ on your website to check the page.'],
  'Keep an existing page’s URL name if you want its current link to keep working. Enter readable content '
  'rather than code.'),
 ('Store settings: identity',
  '33-store',
  'Left menu → Store settings • Owner only',
  ['Update the Store name, Tagline, Phone / WhatsApp and contact Email.',
   'Check the Public contact address customers should use. Ask the owner to handle any legal business '
   'details on bills.',
   'Choose the Brand colour and upload a Logo if needed.',
   'Enter announcements one per line, then scroll through the rest of the form and click Save settings.'],
  'Use a business phone and email customers can contact. A blank logo upload keeps the existing logo.'),
 ('Check the customer website',
  '35-website',
  'Left menu → View website',
  ['Click View website to open the customer-facing site in another tab.',
   'Check Daily menu for the correct date and meal. Check product prices, photos and contact details.',
   'If a saved change looks old, refresh the customer page and check the correct date/tab again.',
   'Return to the admin tab to make any corrections, save them, and check the customer page again.'],
  'Check the customer view after changing a menu, price, photo, banner or page. On a phone, use the menu '
  'button to find the customer navigation.')]

D=Document();sec=D.sections[0];sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width=Cm(29.7);sec.page_height=Cm(21);sec.top_margin=Cm(1.15);sec.bottom_margin=Cm(1.2);sec.left_margin=Cm(1.45);sec.right_margin=Cm(1.45);sec.header_distance=Cm(.45);sec.footer_distance=Cm(.45)
normal=D.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(10.3);normal.font.color.rgb=RGBColor.from_string('2A241F');normal.paragraph_format.space_after=Pt(4)
normal.paragraph_format.line_spacing=1.05
for name,size,color in [('Title',35,'251C16'),('Heading 1',22,'251C16'),('Heading 2',15,'A65000')]:
 st=D.styles[name];st.font.name='Arial';st.font.size=Pt(size);st.font.color.rgb=RGBColor.from_string(color);st.paragraph_format.space_after=Pt(5)
D.core_properties.title='Annam Foods — Admin Panel User Guide';D.core_properties.subject='Screenshots and simple steps for everyday staff tasks';D.core_properties.author='Annam Foods';D.core_properties.keywords='Annam Foods, staff guide, daily operations'
header=sec.header.paragraphs[0];header.text='ANNAM FOODS   /   ADMIN PANEL USER GUIDE';header.runs[0].font.size=Pt(8);header.runs[0].font.color.rgb=RGBColor.from_string('8A6C56')
f=sec.footer.paragraphs[0];f.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=f.add_run('Staff guide · 24 October 2026     |     ');r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('8A6C56')
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');f._p.append(field)
def shade(p,color):
 pr=p._p.get_or_add_pPr();el=OxmlElement('w:shd');el.set(qn('w:fill'),color);pr.append(el)
def note(text):
 p=D.add_paragraph();shade(p,'FFF0DC');r=p.add_run('Remember  ');r.bold=True;r.font.color.rgb=RGBColor.from_string('9B4B00');p.add_run(text);p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(3);return p

def picture(key):
 if key=='18-bill':
  table=D.add_table(rows=1,cols=2);table.autofit=False
  for cell,suffix in zip(table.rows[0].cells,['top','bottom']):
   cell.width=Cm(13.1);p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER
   shape=p.add_run().add_picture(str(ROOT/'screenshots'/('18-bill-'+suffix+'.png')),width=Cm(12.3))
   shape._inline.docPr.set('descr','Bill '+suffix+': logo/customer details or total/print controls')
  return
 path=ROOT/'screenshots'/(key+'.png');w,h=Image.open(path).size;width=26.2;height=width*h/w
 if height>11.65:width=11.65*w/h
 p=D.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(4)
 run=p.add_run();shape=run.add_picture(str(path),width=Cm(width));shape._inline.docPr.set('descr','Actual admin screenshot: '+key)
 return p

# Cover
p=D.add_paragraph();p.paragraph_format.space_before=Pt(12);p.add_run().add_picture(str(ROOT.parents[1]/'php-app/resources/branding/annam-logo.png'),width=Cm(3.8))
p=D.add_paragraph('Your kitchen.\nYour admin guide.','Title');p.paragraph_format.space_before=Pt(8)
p=D.add_paragraph('Simple steps for the Annam Foods team.');p.runs[0].font.size=Pt(17)
p=D.add_paragraph('Menus • Orders • Payments • Bills • WhatsApp • Website');p.runs[0].font.color.rgb=RGBColor.from_string('A65000');p.paragraph_format.space_after=Pt(20)
D.add_paragraph('Everyday staff tasks, with real screenshots and simple steps for menus, orders, bills and website content.')
note('Screenshots come from the running Annam Foods admin preview and use practice records. Actual names, prices, dates and order counts may differ.')
D.add_paragraph('Edition: 24 October 2026  •  Language: simple English')
D.add_page_break()

# Contents: use actual topic page positions (cover=1, contents=2).
D.add_heading('Find what you need',0)
D.add_paragraph('Open the tab shown below, or go straight to the task’s page. Start with the daily checklist at the end if you are running the kitchen today.')
entries=[(title,index+3) for index,(title,*_) in enumerate(TOPICS)]
half=(len(entries)+1)//2
table=D.add_table(rows=1,cols=4);table.autofit=False
for cell,text in zip(table.rows[0].cells,['Task / tab','Page','Task / tab','Page']):
 cell.text=text
 for r in cell.paragraphs[0].runs:r.bold=True;r.font.color.rgb=RGBColor.from_string('A65000')
for i in range(half):
 row=table.add_row();pairs=[entries[i],entries[i+half] if i+half<len(entries) else ('','')]
 for col,(title,page) in zip([0,2],pairs):
  row.cells[col].text=title;row.cells[col+1].text=str(page)
  for c in [row.cells[col],row.cells[col+1]]:
   for para in c.paragraphs:
    para.paragraph_format.space_after=Pt(4)
    for r in para.runs:r.font.size=Pt(9)
for row in table.rows:
 for c,width in zip(row.cells,[11.1,1.5,11.1,1.5]):c.width=Cm(width)
D.add_paragraph(f'Daily checklist: page {len(TOPICS)+3}     •     Common questions: page {len(TOPICS)+4}')
D.add_page_break()

for index,(title,key,breadcrumb,steps,remember) in enumerate(TOPICS,1):
 p=D.add_paragraph(f'{index:02d}   {title}','Heading 1')
 p=D.add_paragraph(breadcrumb);p.runs[0].font.color.rgb=RGBColor.from_string('A65000');p.runs[0].font.size=Pt(9.5)
 picture(key)
 for n,step in enumerate(steps,1):
  p=D.add_paragraph();r=p.add_run(f'{n}.  ');r.bold=True;r.font.color.rgb=RGBColor.from_string('A65000');p.add_run(step);p.paragraph_format.space_after=Pt(3)
 note(remember)
 D.add_page_break()

D.add_heading('Your daily kitchen checklist',0)
D.add_paragraph('Before opening',style='Heading 2')
for text in ['Open Daily menus. Check Today’s date and save breakfast, lunch and dinner separately.','Check the prices and On sale toggles for available products.','Review Meal times and today’s order cutoffs.','Check the active meal Delivery areas and their minimum food values.']:
 D.add_paragraph('☐  '+text)
D.add_paragraph('During the day',style='Heading 2')
for text in ['Watch Orders & billing for new orders.','Check payment status. Confirm offline payments only after the money is received.','Move orders through confirmed, preparing, out for delivery and delivered.','Read WhatsApp messages and create bookings where required.']:
 D.add_paragraph('☐  '+text)
D.add_paragraph('Before finishing',style='Heading 2')
for text in ['Review unpaid orders, cancellations and any refund requests.','Check that eligible paid orders have bills and print/save them when needed.','Prepare tomorrow’s menu if it is ready, then use View website to check it.','Check that all menu and content changes have been saved.']:
 D.add_paragraph('☐  '+text)
D.add_page_break()

D.add_heading('Common questions',0)
faq=[
('My dish does not appear on the customer menu.','Check On sale in Dishes & products. Then open Daily menus, choose the correct date and meal, select the dish and save. Refresh the customer’s menu page.'),
('I want to remove a dish only for one day.','Turn it off in Daily menus for that date and meal, then save. Do not switch the product off globally unless you want it hidden across dates.'),
('The customer cannot place an order.','Check the meal date, pincode, selected delivery area, minimum food value and meal cutoff. Ask the owner if the customer still cannot place the order.'),
('The payment is still pending.','For online payments, use the order’s payment-check action or ask the owner to verify the result. For offline payments, confirm only after receiving the money.'),
('There is no bill.','Check whether payment has been received. An eligible paid order may show Issue bill. Ask the owner if the paid order still has no bill.'),
('A WhatsApp reply is not sending.','Check the message status and 24-hour reply window. Ask the customer to message again if the window is closed. Tell the owner if a reply remains pending.'),
('I cannot confirm a payment or issue a bill.','Your account may not have owner access. Ask the store owner to carry out that action or review your access.'),
('I saved, but the customer page looks unchanged.','Check the success message, refresh the customer page and confirm you are viewing the correct date, meal and product. Ask the owner if it still differs.')]
for question,answer in faq:
 p=D.add_paragraph();r=p.add_run(question);r.bold=True;r.font.color.rgb=RGBColor.from_string('A65000');p.paragraph_format.space_after=Pt(2)
 D.add_paragraph(answer)

# Prevent a screenshot paragraph splitting from its caption; page breaks are explicit.
for para in D.paragraphs:
 para.paragraph_format.widow_control=True
settings=D.settings.element;up=OxmlElement('w:updateFields');up.set(qn('w:val'),'true');settings.append(up)
path=ROOT/'Annam-Foods-Admin-Guide.docx';D.save(path)
(ROOT/'guide-index.json').write_text(json.dumps([{'title':t[0],'screenshot':t[1],'page':i+3} for i,t in enumerate(TOPICS)],indent=2)+'\n')
print('Created',path,'with',len(TOPICS),'illustrated tasks; planned pages',len(TOPICS)+4)
