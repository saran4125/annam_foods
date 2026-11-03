"""Network-free tests for public image discovery; public metadata only."""
from scrape_annam_media import image_urls, public_image_url

html='''<img src="/brand/logo.png"><source srcset="https://cdn.commmerce.com/a.webp 1x, /brand/high.png 2x"><style>.hero{background:url('https://cdn.commmerce.com/banner.jpg')}</style>'''
expected={'https://www.annamfood.in/brand/logo.png','https://cdn.commmerce.com/a.webp','https://www.annamfood.in/brand/high.png','https://cdn.commmerce.com/banner.jpg'}
assert expected <= image_urls(html)
assert image_urls({'gallery':[{'full':'https://cdn.commmerce.com/food.png?x=1&amp;y=2'}]})=={'https://cdn.commmerce.com/food.png?x=1&y=2'}
for value in ['http://cdn.commmerce.com/a.png','https://evil.example/a.png','https://user:password@cdn.commmerce.com/a.png','https://cdn.commmerce.com:444/a.png','/invoice.pdf','data:image/png;base64,hello']:
 assert public_image_url(value) is None,value
print('PASS current public image discovery: gallery, relative/absolute image links, srcset, CSS, query strings and source-host validation')
