"""Test a freshly extracted local SQLite release, without PostgreSQL environment variables."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8125');credentials=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text())
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 response=page.goto(base+'/');assert '/setup/' in page.url,(page.url,page.locator('body').inner_text());assert response.status==200,page.locator('body').inner_text()
 for name,value in {'setup_code':'invalid-code','username':credentials['username'],'password':credentials['password'],'password_confirm':credentials['password']}.items():page.locator('[name='+name+']').fill(value)
 page.get_by_role('button',name='Finish setup').click();assert page.get_by_role('alert').is_visible()
 page.locator('[name=setup_code]').fill(credentials['setup_code'])
 for name in ['username','password','password_confirm']:page.locator('[name='+name+']').fill(credentials['username'] if name=='username' else credentials['password'])
 page.get_by_role('button',name='Finish setup').click();page.wait_for_url('**/manage/login/')
 page.get_by_label('Username',exact=True).fill(credentials['username']);page.get_by_label('Password',exact=True).fill(credentials['password']);page.locator('button[type=submit]').click();page.wait_for_url('**/manage/')
 assert page.get_by_role('heading',name='Kitchen overview',exact=True).is_visible()
 page.goto(base+'/setup/');assert page.url.endswith('/manage/login/'),'Setup was not disabled'
 for path in ['/manage/categories/','/manage/reports/','/manage/orders/','/manage/checkout-settings/','/shop/','/menu/']:
  response=page.goto(base+path);assert response.status==200,(path,page.locator('body').inner_text())
 for path in ['/annam-private/storage/annam.sqlite','/storage/annam.sqlite','/media/test.sqlite','/.env']:
  response=page.goto(base+path);assert response.status in (403,404),(path,response.status)
 assert not errors,errors;browser.close()
print('PASS extracted SQLite ZIP: one-time setup, wrong-code rejection, private owner login, setup disabled, admin/shop/reports and private-path denial')
