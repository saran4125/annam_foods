"""Exercise fixed checkout actions against a disposable localhost meal fixture.
Requires Playwright/Chromium and PINCODE_TEST_BASE, PINCODE_TEST_ITEM,
PINCODE_TEST_DATE as used by check_cart_pincode_browser.py. No real charges.
"""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

base = os.environ['PINCODE_TEST_BASE'].rstrip('/')
assert (urlsplit(base).hostname or '').endswith('localhost')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    for width, height in [(1280, 720), (390, 650)]:
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '/menu/?slot=lunch&date=' + os.environ['PINCODE_TEST_DATE'])
        csrf = page.locator('[name=csrfmiddlewaretoken]').first.input_value()
        response = page.request.post(base + '/cart/add/', form={
            'csrfmiddlewaretoken': csrf, 'item_id': os.environ['PINCODE_TEST_ITEM'],
            'slot_key': 'lunch', 'delivery_date': os.environ['PINCODE_TEST_DATE'],
            'delta': '2', 'next': '/cart/'})
        assert response.status == 200
        page.request.post(base + '/cart/pincode/', form={'csrfmiddlewaretoken': csrf, 'pincode': '600005'})
        page.goto(base + '/checkout/')
        action = page.get_by_role('button', name='Review & place order')
        for position in [0, 500, 10000]:
            page.evaluate('(y)=>scrollTo(0,y)', position)
            box = action.bounding_box()
            assert box and box['y'] >= 0 and box['y'] + box['height'] <= height
        for name, value in dict(name='Browser checkout', phone='9876543210', line1='12 Test Road', city='Chennai').items():
            page.locator('[name=' + name + ']').fill(value)
        page.locator('[name=payment_method]').select_option('manual')
        page.locator('[name=payment_method]').scroll_into_view_if_needed()
        field = page.locator('[name=payment_method]').bounding_box()
        bar = page.locator('.checkout-action-bar').bounding_box()
        assert field['y'] + field['height'] <= bar['y'], 'Last form field is covered'
        action.click()
        expect(page.get_by_role('heading', name='Everything look right?')).to_be_visible()
        final = page.get_by_role('button', name='Place order · ₹330')
        box = final.bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= height
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=f'/tmp/checkout-review-{width}.png', full_page=True)
        final.click()
        page.wait_for_url('**/checkout/complete/**')
        expect(page.get_by_test_id('order-number')).to_be_visible()
        assert not errors, errors
        context.close()
    browser.close()
print('PASS desktop/mobile fixed review and place actions, unobscured form fields, correct total and actual disposable order creation')
