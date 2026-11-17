"""Run against a disposable local fixture with one meal and delivery zones.
Set PINCODE_TEST_BASE, PINCODE_TEST_ITEM and PINCODE_TEST_DATE. Fixture pincodes:
600005: Tiruvallikkeni/10; 600006: Area A/20 and Area B/30; 999999: unsupported.
Requires Playwright and Chromium; writes only to the disposable cart session.
"""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['PINCODE_TEST_BASE'].rstrip('/')
assert (urlsplit(base).hostname or '').endswith('localhost'), 'Use a disposable localhost fixture'
item=os.environ['PINCODE_TEST_ITEM']
delivery_date=os.environ['PINCODE_TEST_DATE']
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page(viewport={'width':1280,'height':720});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/menu/?date='+delivery_date+'&slot=lunch');token=page.locator('[name=csrfmiddlewaretoken]').first.input_value()
 r=page.request.post(base+'/cart/add/',form={'csrfmiddlewaretoken':token,'item_id':item,'slot_key':'lunch','delivery_date':delivery_date,'delta':'2','next':'/cart/'});assert r.status==200,r.text()[:200]
 page.goto(base+'/cart/');url=page.url;page.evaluate('window.noNavigationMarker=42');pin=page.get_by_role('textbox',name='Delivery pincode')
 pin.fill('600005');expect(page.locator('.pincode-box .ok')).to_contain_text('Tiruvallikkeni');expect(page.locator('[data-testid=checkout]')).to_have_attribute('href','/checkout/');assert page.evaluate('noNavigationMarker')==42
 page.get_by_role('button',name='Check',exact=True).click();expect(page.locator('.pincode-box .ok')).to_be_visible();assert page.url==url and page.evaluate('noNavigationMarker')==42
 pin=page.get_by_role('textbox',name='Delivery pincode');pin.fill('999999');expect(page.locator('[data-pincode-feedback]')).not_to_have_text('Checking delivery…');expect(page.locator('[data-testid=checkout]')).to_be_disabled();assert page.locator('.cart-lines').is_visible()
 pin=page.get_by_role('textbox',name='Delivery pincode');pin.fill('600006');expect(page.get_by_role('combobox',name='Your area')).to_be_visible();page.get_by_role('combobox',name='Your area').select_option(label='Area B — ₹30 delivery');expect(page.locator('.pincode-box .ok')).to_contain_text('Area B');expect(page.locator('[data-testid=delivery-charge]')).to_contain_text('30')
 # Type another valid pin while the previous request is still in flight.
 page.route('**/cart/pincode/',lambda route:(page.wait_for_timeout(500),route.continue_()))
 pin=page.get_by_role('textbox',name='Delivery pincode');pin.fill('600005');page.wait_for_timeout(420);pin.fill('600006');page.wait_for_timeout(1500);expect(page.get_by_role('combobox',name='Your area')).to_be_visible()
 page.unroute('**/cart/pincode/');page.get_by_role('combobox',name='Your area').select_option(label='Area A — ₹20 delivery');expect(page.locator('.pincode-box .ok')).to_contain_text('Area A')
 # A network failure keeps content visible and allows a manual retry.
 page.route('**/cart/pincode/',lambda route:route.abort());page.get_by_role('textbox',name='Delivery pincode').fill('600005');expect(page.locator('[data-pincode-feedback]')).to_contain_text('Could not check delivery');assert page.locator('.cart-lines').is_visible();page.unroute('**/cart/pincode/');page.get_by_role('button',name='Check',exact=True).click();expect(page.locator('.pincode-box .ok')).to_contain_text('Tiruvallikkeni')
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path='/tmp/pincode-mobile.png',full_page=True)
 nojs=b.new_context(java_script_enabled=False);nojs.add_cookies(page.context.cookies());fallback=nojs.new_page();fallback.goto(base+'/cart/');fallback.get_by_role('textbox',name='Delivery pincode').fill('600005');fallback.get_by_role('button',name='Check',exact=True).click();expect(fallback.locator('.pincode-box .ok')).to_contain_text('Tiruvallikkeni');assert fallback.locator('.cart-lines').is_visible();nojs.close()
 assert not errors,errors;b.close()
print('PASS automatic pincode, manual check without navigation/blank screen, invalid pin, area selection, rapid edits, network retry and mobile layout')
