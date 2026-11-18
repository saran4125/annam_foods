"""Local-only ZIP fixture: ZIP test lunch tomorrow and 600005 delivery area."""
import os
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['PHP_TEST_BASE'].rstrip('/')
assert urlsplit(base).hostname in ('127.0.0.1','localhost'), 'Use a disposable local fixture'
day=(datetime.now(ZoneInfo('Asia/Kolkata'))+timedelta(days=1)).date().isoformat()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1280,720),(390,650)]:
  c=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/menu/?slot=lunch&date='+day);page.locator('form[data-name="ZIP test lunch"]').get_by_role('button',name='Add',exact=True).click();expect(page.locator('form[data-name="ZIP test lunch"] [data-qty]')).to_have_text('1')
  page.goto(base+'/cart/');page.evaluate('window.sameCartDocument=42');pin=page.locator('[data-pincode-form] [name=pincode]');pin.fill('600005');expect(page.locator('.php-success')).to_be_visible();assert page.evaluate('sameCartDocument')==42
  page.locator('[data-pincode-form] [name=pincode]').fill('999999');expect(page.locator('[data-testid=checkout]')).to_have_attribute('aria-disabled','true');expect(page.locator('[data-pincode-feedback]')).to_contain_text("don't deliver")
  page.locator('[data-pincode-form] [name=pincode]').fill('600005');expect(page.locator('.php-success')).to_be_visible();page.locator('[data-pincode-form] button').click();expect(page.locator('.php-success')).to_be_visible();assert page.evaluate('sameCartDocument')==42
  page.get_by_role('link',name='Checkout →',exact=True).click();page.wait_for_url('**/checkout/');expect(page.locator('[name=pincode]')).to_have_value('600005');action=page.get_by_role('button',name='Review & place order')
  for y in [0,500,10000]:
   page.evaluate('(y)=>scrollTo(0,y)',y);box=action.bounding_box();assert box and box['y']>=0 and box['y']+box['height']<=height
  for k,v in dict(name='ZIP browser test',phone='9876543210',line1='Test address',city='Chennai').items():page.locator('[name='+k+']').fill(v)
  page.locator('[name=payment_method]').select_option('manual');action.click();page.get_by_role('button',name='Place TEST / manual order').click();page.wait_for_url('**/checkout/complete/**');assert page.locator('[data-payment-status]').is_visible();assert not errors,errors;c.close()
 browser.close()
print('PASS ZIP desktop/mobile automatic pincode, invalid pin, manual retry without navigation, prefilled checkout, fixed actions and disposable order')
