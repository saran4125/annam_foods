"""Quantity editor acceptance against a disposable local preview only."""
import json,os
from urllib.parse import urlsplit
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8154').rstrip('/')
assert urlsplit(base).hostname in ('127.0.0.1','localhost')
v=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text())
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=b.new_page(viewport={'width':1440,'height':1000},ignore_https_errors=True)
 page.goto(base+'/manage/login/')
 page.locator('[name=username]').fill(v['username']);page.locator('[name=password]').fill(v['password']);page.locator('button[type=submit]').click()
 page.goto(base+'/manage/dishes/?kind=courier')
 links=page.locator('a[href*="/quantity/"]');print('quantity links',links.count())
 link=links.first.get_attribute('href');page.goto(base+link)
 print(page.title())
 toggle=page.locator('[data-quantity-toggle]');toggle.check(force=True);page.locator('[name=quantity]').fill('5')
 page.screenshot(path='/tmp/inventory-desktop.png',full_page=True)
 page.get_by_role('button',name='Save quantity',exact=True).click()
 page.goto(base+link);expect(page.locator('[data-quantity-toggle]')).to_be_checked();assert page.locator('[name=quantity]').input_value()=='5'
 page.locator('[name=operation]').select_option('add');page.locator('[name=quantity]').fill('3');page.get_by_role('button',name='Save quantity',exact=True).click()
 page.goto(base+link);assert page.locator('[name=quantity]').input_value()=='8'
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400);page.screenshot(path='/tmp/inventory-mobile.png',full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
 page.locator('[data-quantity-toggle]').uncheck(force=True);page.get_by_role('button',name='Save quantity',exact=True).click()
 b.close()
print('PASS quantity editor enable, save, add stock, disable and mobile overflow')
