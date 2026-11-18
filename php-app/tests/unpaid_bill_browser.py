"""Disposable local billing portal acceptance; no live provider calls."""
import json,os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['PHP_TEST_BASE'].rstrip('/')
assert urlsplit(base).hostname in ('127.0.0.1','localhost')
login=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text());item=os.environ['PHP_TEST_ITEM']
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1440,1000),(390,844)]:
  context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce',accept_downloads=True);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/billing/');assert '/billing/login/' in page.url
  page.locator('[name=username]').fill(login['username']);page.locator('[name=password]').fill(login['password']);page.get_by_role('button',name='Sign in →',exact=True).click();page.wait_for_url('**/billing/');expect(page.locator('.o-brand')).to_contain_text('Billing portal')
  for path in ['/billing/','/billing/manual/','/billing/web/','/billing/whatsapp/','/billing/settings/','/billing/new/']:
   response=page.goto(base+path);assert response.status==200,(path,response.status);assert page.url.startswith(base+'/billing/'),page.url;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),path
  page.locator('[name=phone]').fill('9876543210');page.wait_for_timeout(600);page.locator('[name=name]').fill('Collect later portal test');picker=page.locator('[data-line] .b-picker').first;picker.locator('summary').click();picker.get_by_role('button',name='Lunch',exact=True).click();picker.locator('[data-item-id="'+item+'"][data-meal=lunch]').click();expect(page.locator('[name="lines-0-meal"]')).to_have_value('lunch')
  # Collection fixture: clear any address loaded from the phone lookup.
  page.locator('#id_zone').select_option('');page.locator('[name=fulfilment_method]').select_option('');page.get_by_role('button',name='Save order & review total').click();page.wait_for_url('**/billing/orders/*/');url=page.url
  expect(page.get_by_role('button',name='Payment not received · collect on delivery',exact=True)).to_be_visible();page.get_by_role('button',name='Payment not received · collect on delivery',exact=True).click();expect(page.locator('main')).to_contain_text('Payment not received — collect on delivery.');assert page.get_by_role('link',name='View / print bill',exact=False).count()==0
  page.get_by_role('button',name='Issue bill — payment not received',exact=True).click();page.wait_for_url('**/billing/bills/*/');expect(page.locator('.af-receipt-badge')).to_contain_text('UNPAID');bill_unpaid=page.url;page.goto(url)
  with page.expect_download() as download:page.get_by_role('link',name='Download invoice PDF').click()
  download.value.save_as(f'/tmp/unpaid-issued-{width}.pdf')
  # CSRF is enforced independently of browser controls.
  assert page.request.post(url+'payment/',form={'confirmed':'yes'}).status==403
  page.get_by_role('link',name='Manage delivery',exact=True).click()
  for status in ['confirmed','preparing','out_for_delivery','delivered']:
   page.locator('select[name=status]').select_option(status);page.get_by_role('button',name='Update order',exact=True).click()
  page.goto(url);expect(page.locator('main')).to_contain_text('Delivered');expect(page.locator('main')).to_contain_text('Payment not received — collect on delivery.');assert page.get_by_role('link',name='View / print bill',exact=False).count()==1;page.screenshot(path=f'/tmp/php-billing-unpaid-{width}.png',full_page=True)
  page.locator('label.o-check').click();expect(page.locator('[name=confirmed]')).to_be_checked();page.locator('[name=reference]').fill('fixture-cash-collected');page.get_by_role('button',name='Confirm payment received').click();page.wait_for_url('**/billing/bills/*/');expect(page.locator('.af-receipt-badge')).to_contain_text('Payment received');bill=page.url;assert bill==bill_unpaid
  page.goto(url);expect(page.get_by_role('link',name='View / print bill',exact=False)).to_be_visible();assert page.get_by_role('button',name='Payment not received · collect on delivery',exact=True).count()==0
  with page.expect_download() as download:page.get_by_role('link',name='Download invoice PDF').click()
  pdf=download.value;pdf.save_as(f'/tmp/php-billing-invoice-{width}.pdf');assert Path(f'/tmp/php-billing-invoice-{width}.pdf').read_bytes().startswith(b'%PDF-')
  page.goto(base+'/billing/manual/?status=paid&q=Collect');expect(page.locator('main')).to_contain_text('Collect later portal test')
  assert page.request.get(base+'/billing/orders/999999999/').status==404
  assert not errors,errors;context.close()
 browser.close()
print('PASS explicit unpaid bill issuance and same-number collection: PHP dedicated billing overview/channels/settings, meal picker, booking, unpaid COD through delivery, CSRF, confirmation, invoice/PDF, filtering and desktop/mobile layouts')
