"""Local-only staff picker regression; requires BILLING_TEST_BASE and LOGIN JSON."""
import json,os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['BILLING_TEST_BASE'].rstrip('/')
assert (urlsplit(base).hostname or '').endswith('localhost')
login=json.loads(Path(os.environ['BILLING_TEST_LOGIN']).read_text())
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1280,720),(390,844)]:
  page=b.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/billing/login/');page.locator('[name=username]').fill(login['username']);page.locator('[name=password]').fill(login['password']);page.get_by_role('button',name='Sign in',exact=False).click();page.wait_for_url('**/billing/')
  page.goto(base+'/billing/new/');row=page.locator('[data-line]').first;picker=row.locator('.b-picker');picker.locator('summary').click();picker.get_by_role('button',name='Lunch',exact=True).click();picker.locator('button[data-item-id="1"][data-meal="lunch"]').click()
  picker.locator('summary').click();picker.get_by_role('button',name='All',exact=True).click();picker.locator('button[data-item-id="1"][data-meal="breakfast"]').click();expect(row.locator('[name$="-meal"]')).to_have_value('breakfast');picker.locator('summary').click();picker.get_by_role('button',name='Lunch',exact=True).click();picker.locator('button[data-item-id="1"][data-meal="lunch"]').click()
  expect(row.locator('[name$="-meal"]')).to_have_value('lunch');expect(row.locator('[name$="-meal"]')).to_have_attribute('type','hidden');assert row.get_by_text('Food category',exact=True).count()==0
  page.locator('[name=name]').fill('Meal picker test');page.locator('[name=phone]').fill('9876543210');page.get_by_role('button',name='Save order & review total').click();page.wait_for_url('**/billing/orders/*/');assert 'This field is required.' not in page.locator('body').inner_text();assert not errors,errors;page.close()
 b.close()
print('PASS desktop/mobile meal tab sets hidden category and saves staff booking without duplicate category field')
