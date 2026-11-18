"""Disposable localhost acceptance for manual collection after delivery."""
import os,json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['BILLING_TEST_BASE'].rstrip('/')
assert (urlsplit(base).hostname or '').endswith('localhost')
login=json.loads(Path(os.environ['BILLING_TEST_LOGIN']).read_text())
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1440,1000),(390,844)]:
  page=b.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.goto(base+'/billing/login/');page.locator('[name=username]').fill(login['username']);page.locator('[name=password]').fill(login['password']);page.get_by_role('button',name='Sign in',exact=False).click();page.wait_for_url('**/billing/');page.goto(base+'/billing/new/')
  page.locator('[name=phone]').fill('9876543210');page.wait_for_timeout(500);page.locator('[name=name]').fill('Collect later Python test');row=page.locator('[data-line]').first;row.locator('summary').click();row.get_by_role('button',name='Lunch',exact=True).click();row.locator('[data-item-id="1"][data-meal=lunch]').click();page.get_by_role('button',name='Save order & review total').click();page.wait_for_url('**/billing/orders/*/');url=page.url
  page.get_by_role('button',name='Payment not received · collect on delivery',exact=True).click();expect(page.locator('main')).to_contain_text('Payment not received — collect on delivery.');assert page.get_by_role('link',name='View / print bill',exact=False).count()==0
  page.get_by_role('link',name='Manage delivery',exact=True).click()
  for status in ['confirmed','preparing','out_for_delivery','delivered']:
   page.locator('button[name=to][value='+status+']').click()
  page.goto(url);expect(page.locator('main')).to_contain_text('Delivered');expect(page.locator('main')).to_contain_text('Payment not received — collect on delivery.');page.screenshot(path=f'/tmp/python-billing-unpaid-{width}.png',full_page=True)
  page.locator('label.o-check').click();page.locator('[name=reference]').fill('fixture-cash-collected');page.get_by_role('button',name='Confirm payment & issue bill').click();page.wait_for_url('**/billing/bills/*/');expect(page.locator('.af-receipt-badge')).to_contain_text('Payment received');page.close()
 b.close()
print('PASS Python desktop/mobile defer payment, retain unpaid through delivery, then confirm actual collection and issue bill')
