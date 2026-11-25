"""Disposable local catalog flow: creates an item and saves today's test menus."""
import json,time,re,os
from urllib.parse import urlsplit
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
base=os.environ.get('PHP_TEST_BASE','http://127.0.0.1:8154').rstrip('/');assert urlsplit(base).hostname in ('127.0.0.1','localhost');v=json.loads(Path(os.environ['PHP_TEST_LOGIN']).read_text())
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 page=b.new_page(viewport={'width':1440,'height':1000},ignore_https_errors=True,reduced_motion='reduce');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/manage/login/');page.locator('[name=username]').fill(v['username']);page.locator('[name=password]').fill(v['password']);page.locator('button[type=submit]').click()
 page.goto(base+'/manage/categories/');rows=page.locator('tbody tr');assert rows.nth(0).locator('.o-row-title').inner_text()=='Breakfast';assert rows.nth(1).locator('.o-row-title').inner_text()=='Lunch';assert rows.nth(2).locator('.o-row-title').inner_text()=='Dinner';assert rows.nth(3).locator('.o-row-title').inner_text()=='Shop'
 links={key:rows.nth(n).locator('.o-row-title').get_attribute('href') for n,key in enumerate(['breakfast','lunch','dinner','shop'])}
 page.goto(base+links['breakfast']);page.locator('.o-top-actions a.o-btn-primary').click();expect(page.locator('[name=fulfilment]')).to_have_value('scheduled')
 name='One dish three meals '+str(time.time_ns())[-6:];page.locator('[name=name]').fill(name);page.locator('[name=price]').fill('95')
 for key in ['lunch','dinner']:page.locator('[name="meals[]"][value='+key+']').locator('..').click()
 assert page.locator('[name="meals[]"]:checked').count()==3;page.get_by_role('button',name='Save changes').click()
 for key in ['breakfast','lunch','dinner']:
  page.goto(base+links[key]);assert page.get_by_role('link',name=name,exact=True).count()==1,(key,page.locator('main').inner_text())
 page.goto(base+links['shop']);page.locator('.o-top-actions a.o-btn-primary').click();expect(page.locator('[name=fulfilment]')).to_have_value('courier');assert page.locator('[data-meal-assignment]').is_hidden()
 for width in [1440,390]:
  page.set_viewport_size({'width':width,'height':1000});page.goto(base+'/manage/categories/');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=f'/tmp/four-category-{width}.png',full_page=True)
  page.goto(base+links['breakfast']);page.locator('.o-top-actions a.o-btn-primary').click();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=f'/tmp/multi-meal-form-{width}.png',full_page=True)
 page.goto(base+'/billing/new/');catalog=json.loads(page.locator('#billing-catalog').inner_text());item=next(i for i in catalog if i['name']==name);assert sorted(item['groups'])==['breakfast','dinner','lunch']
 page.goto(base+'/manage/dishes/menu/');page.get_by_role('navigation',name='Meal',exact=True).get_by_role('link',name='Breakfast',exact=True).click();choice=page.locator('[data-daily-choice]').filter(has=page.get_by_text(name,exact=True));assert choice.count()==1 and not choice.locator('[type=checkbox]').is_checked();choice.click();page.get_by_role('button',name=re.compile('^Save .* menu$')).click();assert page.locator('[data-daily-choice]').filter(has=page.get_by_text(name,exact=True)).locator('[type=checkbox]').is_checked()
 page.get_by_role('navigation',name='Meal',exact=True).get_by_role('link',name='Lunch',exact=True).click();choice=page.locator('[data-daily-choice]').filter(has=page.get_by_text(name,exact=True));assert not choice.locator('[type=checkbox]').is_checked();choice.click();page.get_by_role('button',name=re.compile('^Save .* menu$')).click()
 assert not errors,errors;print('PASS four defaults first, one dish in all three libraries, Shop defaults to shop products, multi-meal form and mobile layouts');b.close()
