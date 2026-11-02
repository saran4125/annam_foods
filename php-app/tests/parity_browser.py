"""Real browser acceptance for an isolated preview; credentials stay in a private JSON file."""
import json,os,re
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8120')
login=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text())
artifacts=Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-parity-review'));artifacts.mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/manage/');page.get_by_label('Username',exact=True).fill(login['username']);page.get_by_label('Password',exact=True).fill(login['password']);page.locator('button[type=submit]').click();page.wait_for_url('**/manage/')
 for path,heading in [('/manage/categories/','Categories'),('/manage/dishes/?kind=courier','Dishes & products'),('/manage/reports/','Order reports & sales'),('/manage/orders/','Orders & billing'),('/manage/checkout-settings/','Checkout settings'),('/manage/orders/new/','Create booking')]:
  response=page.goto(base+path);assert response.status==200,(path,page.locator('body').inner_text());assert page.get_by_role('heading',name=heading,exact=True).is_visible()
 page.goto(base+'/manage/categories/');assert page.get_by_text('Empty categories',exact=True).is_visible();page.get_by_role('link',name='Manage items',exact=True).first.click();assert page.locator('.o-table tbody tr').count()>0;page.screenshot(path=str(artifacts/'category-items.png'),full_page=True)
 date=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)).strftime('%Y-%m-%d')
 page.goto(base+'/manage/dishes/menu/?date='+date)
 slots=page.locator('nav[aria-label=Meal] a').evaluate_all('(links)=>links.map(o=>({id:new URL(o.href).searchParams.get("slot_id"),label:o.textContent}))')
 for label in ['Breakfast','Lunch']:
  slot=next(s for s in slots if s['label'].strip()==label)
  page.goto(base+'/manage/dishes/menu/?date='+date+'&slot_id='+slot['id']);picks=page.locator('label.php-menu-pick input[type=checkbox]');assert picks.count()>0
  for n in range(min(4,picks.count())):
   if not picks.nth(n).is_checked():picks.nth(n).locator('..').click()
   assert picks.nth(n).is_checked()
  page.locator('button[type=submit]').last.click();assert 'saved' in page.locator('body').inner_text().lower()
  page.goto(base+'/menu/?date='+date)
  section=page.locator('section.php-store-section').filter(has=page.get_by_role('heading',name=label,exact=True)).last
  section.get_by_role('button',name='Add',exact=True).first.click();assert page.get_by_role('heading',name='Your cart',exact=True).is_visible()
 assert 'Breakfast + Lunch' in page.locator('body').inner_text() or 'Lunch + Breakfast' in page.locator('body').inner_text()
 page.locator('input[name=pincode]').fill('600005');page.get_by_role('button',name='Check delivery',exact=True).click();assert 'One delivery charge applies' in page.locator('body').inner_text()
 page.get_by_role('link',name='Checkout →').click()
 for key,value in {'name':'Parity Customer','phone':'9999999999','line1':'12 Test Street','city':'Chennai','pincode':'600005'}.items():page.locator('[name='+key+']').fill(value)
 page.get_by_role('button',name='Review order').click();assert page.get_by_role('heading',name='Review your order').is_visible();page.get_by_role('button',name='Place order').click();assert '/checkout/complete/' in page.url
 page.goto(base+'/manage/orders/');page.get_by_role('link',name=re.compile('ANNAM-')).first.click();page.get_by_label('Payment reference',exact=True).fill('isolated-browser-receipt');page.get_by_label('I confirm the payment was received',exact=True).locator('..').click();page.get_by_role('button',name='Confirm payment',exact=True).click();page.get_by_role('link',name='View / print bill',exact=True).click();assert page.locator('.af-receipt-logo').is_visible();assert 'Delivery fee' in page.locator('body').inner_text();page.screenshot(path=str(artifacts/'combined-meal-bill.png'),full_page=True)
 page.goto(base+'/manage/orders/new/');page.locator('#customer-phone').fill('9999999999');page.wait_for_function("document.querySelector('#customer-lookup-status').textContent.includes('filled')");assert page.locator('#customer-name').input_value()=='Parity Customer';assert '12 Test Street' in page.locator('#customer-address').input_value();page.locator('#customer-address').fill('Edited address');assert page.locator('#customer-address').input_value()=='Edited address'
 page.goto(base+'/manage/reports/');assert page.locator('.o-table tbody tr').count()>0;page.screenshot(path=str(artifacts/'reports.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.goto(base+'/shop/');assert page.locator('.dish').count()<=36
 assert not errors,errors
 browser.close()
print('PASS real browser: category items, dated menus, combined checkout, one fee, paid bill, editable phone lookup, reports and mobile shop')
