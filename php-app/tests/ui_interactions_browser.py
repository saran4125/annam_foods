"""Exercise responsive shelves, stock-aware cart controls and no-JavaScript fallback."""
import os,re
from playwright.sync_api import sync_playwright
base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8120')
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1920,'height':1080},reduced_motion='reduce')
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 assert page.goto(base+'/').status==200
 assert page.locator('.cart-link').bounding_box()['width']<150
 assert page.locator('[data-cart-count]').is_hidden()
 assert re.search(r'\?v=[a-f0-9]{12}',page.locator('link[href*="python-ui.css"]').get_attribute('href'))
 assert len(page.locator('.dishes').first.evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ")'))==6
 shelf=page.locator('[data-shelf-row]');shelf.scroll_into_view_if_needed();page.wait_for_timeout(300)
 assert page.locator('[data-shelf-prev]').is_disabled()
 if shelf.evaluate('(el)=>el.scrollWidth>el.clientWidth'):
  page.locator('[data-shelf-next]').click();page.wait_for_function("document.querySelector('[data-shelf-row]').scrollLeft>10")
  assert page.locator('[data-shelf-prev]').is_enabled()
 # Load lazy media before validating it, including images beyond the viewport.
 for img in page.locator('img').all():
  img.scroll_into_view_if_needed();img.evaluate('(el)=>el.loading="eager"')
 page.wait_for_function('Array.from(document.images).every(i=>i.complete)')
 assert page.locator('img').evaluate_all('(images)=>images.every(i=>i.naturalWidth>0)'), 'An assigned photograph failed to load'
 page.goto(base+'/shop/')
 form=page.locator('[data-cart-form]').first
 for button,quantity in [('Add',1),('One more',2),('One fewer',1),('One fewer',0)]:
  with page.expect_response(lambda r:'/cart/add/' in r.url and r.request.method=='POST') as result:
   form.get_by_role('button',name=re.compile('^'+button)).click()
  assert result.value.status==200,result.value.text()
  assert result.value.json()['quantity']==quantity
  page.wait_for_function('!document.querySelector("[data-cart-form][aria-busy=true]")')
  assert page.locator('[data-cart-count]').inner_text()==str(quantity)
 assert page.locator('[data-cart-count]').is_hidden()
 assert page.locator('[data-cart-bar]').is_hidden()
 assert not errors,errors
 plain=browser.new_context(java_script_enabled=False)
 fallback=plain.new_page();fallback.goto(base+'/shop/');fallback.locator('[data-cart-form]').first.get_by_role('button',name='Add',exact=True).click();fallback.wait_for_url('**/cart/')
 assert fallback.get_by_role('heading',name='Your order',exact=True).is_visible()
 browser.close()
print('PASS compact header, versioned assets, six-column desktop grid, shelf arrows, assigned photos, AJAX add/plus/minus/remove and ordinary POST fallback')
