"""Local-only staff booking test for a fixture item assigned to one meal."""
import json,os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['PHP_TEST_BASE'].rstrip('/')
assert urlsplit(base).hostname in ('127.0.0.1','localhost')
login=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text());item=os.environ['PHP_TEST_ITEM']
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page()
 page.goto(base+'/manage/login/');page.get_by_label('Username',exact=True).fill(login['username']);page.get_by_label('Password',exact=True).fill(login['password']);page.locator('button[type=submit]').click();page.wait_for_url('**/manage/')
 page.goto(base+'/manage/orders/new/');quantity=page.locator('[name="quantities['+item+']"]');row=quantity.locator('..');assert row.locator('select').count()==0;expect(row.locator('[name="meals['+item+']"]')).to_have_attribute('type','hidden');expect(row.locator('[name="meals['+item+']"]')).to_have_value('lunch')
 page.locator('[name=phone]').fill('9876543210');page.wait_for_timeout(500);page.locator('[name=name]').fill('Category picker test');quantity.fill('1');page.get_by_role('button',name='Create unpaid booking').click();page.wait_for_url('**/manage/orders/*/');assert 'This field is required.' not in page.locator('body').inner_text();b.close()
print('PASS PHP single-meal item has no duplicate category dropdown and creates staff order')
