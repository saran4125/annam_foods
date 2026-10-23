import os,re
from pathlib import Path
from playwright.sync_api import sync_playwright
credentials={'username':os.environ['PHP_TEST_USERNAME'],'password':os.environ['PHP_TEST_PASSWORD']}
Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')).mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1050},reduced_motion='reduce')
 errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8091/manage/');page.get_by_label('Username',exact=True).fill(credentials['username']);page.get_by_label('Password',exact=True).fill(credentials['password']);page.locator('button[type=submit]').click();page.wait_for_url('**/manage/')
 assert page.get_by_role('heading',name='Kitchen overview').is_visible()
 page.get_by_role('link',name='Daily menus',exact=True).click();page.get_by_role('link',name='Tomorrow',exact=True).click()
 assert page.get_by_role('link',name='Tomorrow',exact=True).get_attribute('class')=='selected'
 for text in ['Idly (4)','Ghee Podi Dosa (2)','Ghee Pongal','Plain Dosa (2)','Idly with Vadai']:
  rows=page.locator('label.php-menu-pick').filter(has_text=text)
  if rows.count() and not rows.first.locator('input[type=checkbox]').is_checked(): rows.first.click()
 page.get_by_role('button',name=re.compile('Save .* menu')).click()
 assert page.locator('p.o-flash').is_visible()
 page.screenshot(path=str(Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')) / 'admin-menu.png'),full_page=True)
 date=page.locator('input[name=date]').first.input_value()
 page.goto('http://127.0.0.1:8091/menu/?date='+date)
 assert page.locator('.dish').count()>0
 page.locator('.dish').first.get_by_role('button',name='Add',exact=True).click()
 assert page.get_by_role('heading',name='Your cart',exact=True).is_visible()
 page.get_by_role('textbox',name='Pincode',exact=True).fill('600005')
 page.get_by_role('button',name='Check delivery',exact=True).click()
 assert page.get_by_text('This order meets the area minimum.').is_visible()
 assert page.get_by_role('button',name='Checkout not live in this preview').is_disabled()
 page.screenshot(path=str(Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')) / 'cart-delivery.png'),full_page=True)
 page.goto('http://127.0.0.1:8091/manage/dishes/new/')
 page.get_by_role('textbox',name='Name',exact=True).fill('Browser test dish')
 page.get_by_label('Price (₹)',exact=True).fill('123.45')
 page.get_by_role('button',name='Save changes').click()
 assert page.get_by_text('Browser test dish',exact=True).first.is_visible()
 page.goto('http://127.0.0.1:8091/manage/zones/');assert page.get_by_text('Teynampet',exact=True).is_visible()
 page.screenshot(path=str(Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')) / 'admin-zones.png'),full_page=True)
 page.goto('http://127.0.0.1:8091/');page.screenshot(path=str(Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')) / 'storefront.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.goto('http://127.0.0.1:8091/manage/');page.locator('[data-burger]').click();assert page.locator('[data-side]').get_attribute('class').find('is-open')>=0
 page.screenshot(path=str(Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-php-review')) / 'admin-mobile.png'),full_page=True)
 assert not errors,errors
 browser.close()
print('PASS browser login, date selection/save, storefront/cart minimum, product creation, zones and mobile navigation')
