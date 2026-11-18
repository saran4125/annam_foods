"""Local-only website manual-payment vs online-payment billing regression."""
import json,os,re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
base=os.environ['BILLING_TEST_BASE'].rstrip('/')
assert urlsplit(base).hostname in ('localhost','127.0.0.1') or (urlsplit(base).hostname or '').endswith('.localhost')
login=json.loads(Path(os.environ['BILLING_TEST_LOGIN']).read_text());cases=json.loads(Path(os.environ['BILLING_TEST_CASES']).read_text())
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(1440,1000),(390,844)]:
  page=b.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.goto(base+'/billing/login/');page.locator('[name=username]').fill(login['username']);page.locator('[name=password]').fill(login['password']);page.get_by_role('button',name=re.compile('Sign in')).click();page.wait_for_url('**/billing/')
  page.goto(base+'/billing/orders/'+str(cases['manual'])+'/');button=page.get_by_role('button',name='Payment not received · collect on delivery',exact=True);expect(button).to_be_visible();page.screenshot(path=f'/tmp/website-manual-collection-{urlsplit(base).port}-{width}.png',full_page=True);button.click();expect(page.locator('main')).to_contain_text('Payment not received — collect on delivery.');assert page.get_by_role('link',name='View / print bill',exact=False).count()==0
  page.goto(base+'/billing/orders/'+str(cases['online'])+'/');expect(page.locator('main')).to_contain_text('Payment not received.');assert page.get_by_role('button',name='Payment not received · collect on delivery',exact=True).count()==0;assert page.get_by_role('button',name='Confirm payment & issue bill').count()==0;page.close()
 b.close()
print('PASS desktop/mobile website manual-payment collection option visible; online website orders show unpaid status with manual settlement blocked')
