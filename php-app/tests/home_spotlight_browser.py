"""Verify the bundled Health Mix artwork without relying on uploaded media."""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['PHP_TEST_BASE'].rstrip('/')
assert urlsplit(base).hostname in ('127.0.0.1','localhost'), 'Use a disposable local fixture'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1280,720),(390,844)]:
  page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base+'/',wait_until='domcontentloaded');feature=page.locator('[data-home-section=spotlight] .feature');feature.scroll_into_view_if_needed();image=feature.locator('.feature-art img');expect(image).to_be_visible();expect(image).to_have_js_property('complete',True);assert image.evaluate('(i)=>i.naturalWidth>0');assert page.request.get(image.evaluate('(i)=>i.src')).status==200
  expect(feature.locator('.feature-badge')).to_be_visible();expect(feature.locator('.feature-list-title')).to_contain_text('17 ingredients');assert feature.locator('.feature-list li').count()==17;expect(feature.get_by_role('link',name='Order Health Mix')).to_have_attribute('href','/item/231/')
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=f'/tmp/php-health-mix-{width}.png',full_page=True);feature.screenshot(path=f'/tmp/php-health-mix-section-{width}.png');assert not errors,errors;page.close()
 browser.close()
print('PASS desktop/mobile Health Mix photo, badge, 17 ingredients, order link and responsive layout without uploaded media')
