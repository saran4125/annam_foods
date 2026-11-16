"""Visual component and functional smoke checks for the Python-to-PHP UI port."""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8120')
login=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text())
artifacts=Path(os.environ.get('PHP_REVIEW_ARTIFACTS','/tmp/annam-python-ui-review'));artifacts.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base+'/manage/login/')
    assert page.locator('.lg-brand').is_visible() and page.locator('.lg-input').count()==2
    page.screenshot(path=str(artifacts/'login-desktop.png'),full_page=True,animations='disabled')
    page.get_by_label('Username',exact=True).fill(login['username']);page.get_by_label('Password',exact=True).fill(login['password'])
    page.get_by_role('button',name='Show password',exact=True).click();assert page.locator('[name=password]').get_attribute('type')=='text'
    page.locator('button[type=submit]').click();page.wait_for_url('**/manage/')
    for name,path in [('dashboard','/manage/'),('breakfast','/manage/dishes/?kind=scheduled&meal=breakfast&date=all'),('menu-editor','/manage/dishes/menu/'),('categories','/manage/categories/'),('edit','/manage/dishes/new/?kind=scheduled'),('orders','/manage/orders/'),('reports','/manage/reports/'),('checkout-settings','/manage/checkout-settings/'),('settings','/manage/settings/'),('home','/'),('about','/about/'),('shop','/shop/'),('daily-menu','/menu/'),('cart','/cart/')]:
        response=page.goto(base+path);assert response.status==200,(name,response.status)
        page.screenshot(path=str(artifacts/(name+'-desktop.png')),full_page=True,animations='disabled')
    page.goto(base+'/manage/dishes/?kind=scheduled&meal=breakfast&date=all')
    assert page.locator('.o-catalog-groups').is_visible() and page.locator('.o-thumb img').count()>0
    row=page.locator('.o-table tbody tr').first;stock=row.get_by_role('switch',name='Stock ',exact=False)
    checked=stock.get_attribute('aria-checked');stock.click();page.wait_for_load_state()
    assert page.locator('.o-table tbody tr').first.get_by_role('switch',name='Stock ',exact=False).get_attribute('aria-checked')!=checked
    page.locator('.o-table tbody tr').first.get_by_role('switch',name='Stock ',exact=False).click();page.wait_for_load_state()
    page.goto(base+'/manage/dishes/menu/');search=page.get_by_role('searchbox',name='Find a dish',exact=True);search.fill('unlikely-dish-xxxxxxxx')
    assert page.locator('[data-daily-choice]:visible').count()==0;search.fill('')
    page.goto(base+'/shop/?sort=price')
    prices=page.locator('.dish .price').all_text_contents();numbers=[float(v.replace('₹','').replace(',','')) for v in prices];assert numbers==sorted(numbers)
    page.set_viewport_size({'width':390,'height':844})
    for name,path in [('home','/'),('about','/about/'),('shop','/shop/'),('dashboard','/manage/'),('breakfast','/manage/dishes/?kind=scheduled&meal=breakfast&date=all')]:
        response=page.goto(base+path);assert response.status==200
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),name
        page.screenshot(path=str(artifacts/(name+'-mobile.png')),full_page=True,animations='disabled')
    page.goto(base+'/');page.get_by_role('button',name='Open menu',exact=True).click();assert page.locator('[data-mobile-nav]').is_visible()
    page.goto(base+'/manage/');page.get_by_role('button',name='Open menu',exact=True).click();assert page.locator('.o-side').evaluate('(el)=>el.classList.contains("is-open")')
    assert not errors,errors
    browser.close()
print('PASS Python-style login/sidebar/dashboard/catalog/forms, stock POST, dish search, shop sorting, desktop/mobile layout and navigation')
