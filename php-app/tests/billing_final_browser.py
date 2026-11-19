"""Local-only full billing and final-document acceptance. Never targets production."""
from pathlib import Path
import json,time,os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
root=Path(os.environ.get('PHP_TEST_OUTPUT','/tmp/annam-billing-final-audit'));root.mkdir(parents=True,exist_ok=True);values=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text());base=os.environ['PHP_TEST_BASE'].rstrip('/');assert urlsplit(base).hostname in ('127.0.0.1','localhost');results=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (1440,390):
  c=b.new_context(viewport={'width':width,'height':1000},ignore_https_errors=True,reduced_motion='reduce',accept_downloads=True);page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/billing/login/');page.locator('[name=username]').fill(values['username']);page.locator('[name=password]').fill(values['password']);page.locator('button').last.click();page.wait_for_url('**/billing/')
  for path in ('/billing/','/billing/manual/','/billing/web/','/billing/whatsapp/','/billing/settings/','/billing/new/'):
   response=page.goto(base+path);assert response.status==200;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,path)
  catalog=json.loads(page.locator('#billing-catalog').inner_text());lunch=next(i for i in catalog if i['name']=='Full meals with rice');breakfast=next(i for i in catalog if i['name']=='Idly (4)');name=f'Final billing audit {width} '+str(time.time_ns())[-5:]
  page.locator('[name=phone]').fill('9876543001');page.wait_for_timeout(600);page.locator('[name=name]').fill(name);page.locator('#id_zone').select_option('');page.locator('[name=fulfilment_method]').select_option('');page.locator('[name=payment_mode]').select_option('cod')
  for n,(item,meal) in enumerate(((lunch,'lunch'),(breakfast,'breakfast'))):
   if n:page.locator('#add-line').click()
   picker=page.locator('[data-line] .b-picker').nth(n)
   if picker.get_attribute('open') is None:picker.locator('summary').click()
   picker.get_by_role('button',name=meal.capitalize(),exact=True).click();picker.locator('[data-item-id="'+str(item['id'])+'"][data-meal='+meal+']').click()
  page.locator('[name="lines-0-quantity"]').fill('2');data=page.locator('#booking-form').evaluate('(f)=>Object.fromEntries(new FormData(f))');data['name']='';r=page.request.post(base+'/billing/new/',form=data);assert r.status==422 and 'Enter the customer name' in r.text() and '9876543001' in r.text() and str(lunch['id']) in r.text();results.append((width,'invalid booking retains values'))
  page.get_by_role('button',name='Save order & review total').click();page.wait_for_url('**/billing/orders/*/');order=page.url;expect(page.locator('main')).to_contain_text('Booking details');expect(page.locator('main')).to_contain_text('Final total');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(root/f'booking-review-{width}.png'),full_page=True)
  # Missing receipt acknowledgement gives a recoverable error on this order.
  csrf=page.locator('main [name=csrf]').first.input_value();r=page.request.post(order+'payment/',form={'csrf':csrf});assert r.status==200 and 'o-flash-error' in r.text();page.reload()
  page.get_by_role('button',name='Issue bill — payment not received',exact=True).click();page.wait_for_url('**/billing/bills/*/');bill=page.url;expect(page.locator('.af-receipt-badge')).to_contain_text('UNPAID');expect(page.locator('.af-receipt')).to_contain_text('Amount due');assert page.get_by_role('link',name='Back to order',exact=True).get_attribute('href')==order.removeprefix(base);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(root/f'unpaid-bill-{width}.png'),full_page=True)
  with page.expect_download() as download:page.get_by_role('link',name='Download PDF',exact=True).click()
  download.value.save_as(str(root/f'unpaid-{width}.pdf'));page.emulate_media(media='print');expect(page.locator('.bill-actions')).not_to_be_visible();page.pdf(path=str(root/f'print-{width}.pdf'),format='A4');page.emulate_media(media='screen')
  page.get_by_role('link',name='Back to order',exact=True).click();page.locator('label.o-check').click();page.locator('[name=reference]').fill('LOCAL-CASH-COLLECTED');page.get_by_role('button',name='Confirm payment received',exact=True).click();page.wait_for_url('**/billing/bills/*/');assert page.url==bill;expect(page.locator('.af-receipt-badge')).to_contain_text('Payment received');assert 'Amount due' not in page.locator('.af-receipt').inner_text();page.screenshot(path=str(root/f'paid-bill-{width}.png'),full_page=True)
  with page.expect_download() as download:page.get_by_role('link',name='Download PDF',exact=True).click()
  download.value.save_as(str(root/f'paid-{width}.pdf'));page.get_by_role('link',name='Back to order',exact=True).click();expect(page.get_by_role('link',name='View / print bill',exact=False)).to_be_visible()
  page.goto(base+'/billing/settings/');data=page.locator('main form').evaluate('(f)=>Object.fromEntries(new FormData(f))');data['fssai_no']='bad';r=page.request.post(base+'/billing/settings/',form=data);assert r.status==422 and 'o-flash-error' in r.text() and 'value="bad"' in r.text();assert not errors,errors;results.append((width,'booking, review, unpaid/paid bill, same invoice, return links, PDF and print, settings errors'));c.close()
 b.close()
(root/'checks.json').write_text(json.dumps(results,indent=2));print('PASS billing page and full mixed-meal booking/receipt/PDF/print/error checks at desktop and mobile widths')
