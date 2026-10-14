/* Standalone local design preview. No checkout or customer data is submitted. */
(() => {
  'use strict';
  const main = document.querySelector('#main');
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const storageKey = 'annam-preview-cart-v2';
  let catalog, products, cart = {}, toastTimer, observer;
  let category = 'all', query = '', sort = 'featured';
  // Integer paise keep cart arithmetic exact; source prices remain decimal strings.
  const paise = price => { const [rupees, fraction = ''] = String(price).split('.'); return Number(rupees) * 100 + Number(fraction.padEnd(2, '0').slice(0, 2)); };
  const money = amount => '₹' + (amount / 100).toLocaleString('en-IN', {maximumFractionDigits:2});
  const price = product => money(paise(product.price));
  const product = id => products.find(item => item.id === id);
  const img = (item, extra = '') => `<img src="${escape(item.image)}" alt="${escape(item.name)}" ${extra}>`;
  const routeLink = (href, label, cls = 'text-link') => `<a href="${href}" data-route class="${cls}">${label}</a>`;
  function quantities(item) {
    const qty = cart[item.id] || 0;
    if (!item.available) return '<button class="add" disabled>Unavailable</button>';
    if (!qty) return `<button class="add" data-add="${escape(item.id)}" aria-label="Add ${escape(item.name)} to cart">Add +</button>`;
    return `<div class="quantity"><button data-delta="-1" data-id="${escape(item.id)}" aria-label="Decrease ${escape(item.name)} quantity">−</button><span aria-label="Quantity">${qty}</span><button data-delta="1" data-id="${escape(item.id)}" aria-label="Increase ${escape(item.name)} quantity" ${qty >= 20 ? 'disabled' : ''}>+</button></div>`;
  }
  function card(item) {
    return `<article class="product-card" data-product="${escape(item.id)}"><a class="product-photo" href="${escape(item.source_url)}" target="_blank" rel="noopener" aria-label="View ${escape(item.name)} on Annam Foods">${img(item,'loading="lazy" width="500" height="500"')}<span class="veg-dot" aria-label="Vegetarian"></span>${!item.available ? '<span class="stock-label">Out of stock</span>' : ''}</a><div class="product-info"><p class="product-kind">${escape(item.category_label)}</p><h3 class="product-title">${escape(item.name)}</h3><div class="product-bottom"><span class="price">${price(item)}</span><div data-controls="${escape(item.id)}">${quantities(item)}</div></div></div></article>`;
  }
  function heading(title, intro, kicker = '') {
    return `<div class="page-title"><div class="breadcrumb">${routeLink('/','Home','')}<span>/</span><span>${escape(title)}</span></div>${kicker ? `<p class="eyebrow">${escape(kicker)}</p>` : ''}<h1>${escape(title)}</h1><p>${intro}</p></div>`;
  }
  function home() {
    const halwa = product('tirunelveli-halwa'), savoury = product('thenkuzal'), idly = product('25-03-2023-saturday-idly-4');
    const selected = ['idly-with-vadai','dosa-2','tirunelveli-halwa','thenkuzal'].map(product).filter(Boolean);
    const categoryImages = ['25-03-2023-saturday-idly-4','11th-with-rice-1','tirunelveli-halwa','thenkuzal','pirandai-podi','diwali-mega-combo-pck'];
    main.innerHTML = `<div class="wrap"><section class="hero"><div class="hero-copy"><p class="eyebrow">Chennai’s Annam Foods</p><h1>Good food.<br>Familiar flavours.<br><em>A taste of home.</em></h1><p>From soft idlis and comforting meals to traditional sweets and crisp savouries. Find a little something for every craving.</p><div class="hero-actions">${routeLink('/menu/','Explore the menu <span aria-hidden="true">↗</span>','button')}${routeLink('/menu/?category=sweets','Something sweet <span aria-hidden="true">→</span>')}</div><div class="hero-note"><span class="veg-dot" aria-hidden="true"></span>Vegetarian favourites, from Annam’s kitchen.</div></div><div class="hero-visual">${img(halwa,'class="hero-photo" fetchpriority="high" width="500" height="500"')}${img(savoury,'class="hero-inset" width="500" height="500"')}<div class="photo-caption"><span>Sweet traditions</span>Spl Tirunelveli Ghee Halwa</div></div></section><section class="values" aria-label="Explore Annam"><div class="value"><span class="value-number">01</span><div><h3>Everyday comfort</h3><p>Breakfast favourites and complete lunch meals.</p></div></div><div class="value"><span class="value-number">02</span><div><h3>Traditional treats</h3><p>Sweets, savouries and familiar pantry staples.</p></div></div><div class="value"><span class="value-number">03</span><div><h3>A little celebration</h3><p>Discover Annam’s Diwali 2026 collection.</p></div></div></section><section class="section reveal"><div class="section-head"><div><p class="eyebrow">What are you craving?</p><h2>Find your favourite.</h2></div>${routeLink('/menu/','Browse all <span aria-hidden="true">→</span>')}</div><div class="category-grid">${catalog.categories.map((cat,i) => `<a class="category" href="/menu/?category=${cat.id}" data-route><div class="category-photo">${img(product(categoryImages[i]),'loading="lazy" width="500" height="500"')}</div><strong>${escape(cat.label)}</strong><small>${products.filter(p=>p.category===cat.id).length} dishes to explore</small></a>`).join('')}</div></section><section class="section reveal" style="padding-top:0"><div class="section-head"><div><p class="eyebrow">From the Annam kitchen</p><h2>A few favourites to start.</h2></div>${routeLink('/menu/','See the menu <span aria-hidden="true">→</span>')}</div><div class="product-grid">${selected.map(card).join('')}</div></section><a class="campaign reveal" style="display:block" href="/menu/?category=diwali" data-route aria-label="Explore the Diwali 2026 collection"><picture><source media="(max-width:760px)" srcset="${catalog.brand.campaign_mobile}"><img src="${catalog.brand.campaign}" alt="Annam Foods Diwali 2026 collection" loading="lazy"></picture></a><section class="story-panel reveal">${img(idly,'loading="lazy" width="500" height="500"')}<div class="story-copy"><p class="eyebrow">Rooted in familiar flavours</p><h2>For the everyday.<br>And the special days.</h2><p>A breakfast that feels like home. Something crisp with your evening tea. A box of sweets to share. Explore the flavours that make Annam, Annam.</p>${routeLink('/p/about/','Meet Annam Foods <span aria-hidden="true">→</span>')}</div></section></div>`;
  }
  function menu() {
    const chosen = new URLSearchParams(location.search).get('category');
    category = catalog.categories.some(cat=>cat.id===chosen) ? chosen : 'all'; query = ''; sort = 'featured';
    main.innerHTML = `<div class="wrap">${heading('The Annam menu.','Everyday meals, traditional treats and festive favourites. Find what you’re in the mood for.','Explore the kitchen')}<div class="menu-toolbar"><label class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg><input id="search" type="search" placeholder="Search idly, halwa, podi…" aria-label="Search dishes"></label><label class="sort">Sort by <select id="sort" aria-label="Sort dishes"><option value="featured">Catalog order</option><option value="low">Price: low to high</option><option value="high">Price: high to low</option><option value="name">Name: A to Z</option></select></label></div><div class="filters" role="group" aria-label="Dish categories">${[{id:'all',label:'All dishes'},...catalog.categories].map(cat=>`<button class="filter" data-category="${cat.id}" aria-pressed="${category===cat.id}">${escape(cat.label)}</button>`).join('')}</div><div class="results-head"><span id="result-count" role="status" aria-live="polite"></span><span>Original Annam photos & prices</span></div><div id="menu-grid" class="product-grid"></div><p class="catalog-note">Catalog snapshot from Annam Foods. Daily meal dates, stock and prices may change; confirm them on the original site before ordering.</p></div>`;
    renderResults();
  }
  function renderResults() {
    let found = products.filter(item => (category==='all'||item.category===category) && (item.name+' '+item.category_label+' '+item.description).toLowerCase().includes(query.toLowerCase().trim()));
    if (sort==='low') found.sort((a,b)=>paise(a.price)-paise(b.price));
    if (sort==='high') found.sort((a,b)=>paise(b.price)-paise(a.price));
    if (sort==='name') found.sort((a,b)=>a.name.localeCompare(b.name));
    document.querySelector('#result-count').textContent = `${found.length} ${found.length===1?'dish':'dishes'}${category!=='all'?' · '+catalog.categories.find(cat=>cat.id===category).label:''}`;
    document.querySelector('#menu-grid').innerHTML = found.length ? found.map(card).join('') : `<div class="empty"><h2>No dishes found.</h2><p>Try a different name or browse all categories.</p><button class="button secondary" data-reset>Clear filters</button></div>`;
  }
  function cartPage() {
    const items = products.filter(item=>cart[item.id]);
    const subtotal = items.reduce((sum,item)=>sum+paise(item.price)*cart[item.id],0);
    main.innerHTML = `<div class="wrap">${heading('Your cart.','A little comfort, ready to gather.','Your favourites')}${!items.length ? `<div class="empty"><h2>Your table is waiting.</h2><p>Add a few favourites from the menu to get started.</p>${routeLink('/menu/','Explore the menu →','button')}</div>` : `<div class="cart-layout"><div class="cart-items">${items.map(item=>`<article class="cart-row">${img(item,'width="90" height="90"')}<div><h3>${escape(item.name)}</h3><p class="product-kind">${escape(item.category_label)} · ${price(item)} each</p><button class="remove" data-remove="${escape(item.id)}" aria-label="Remove ${escape(item.name)} from cart">Remove</button></div><div class="cart-row-end"><span class="price">${money(paise(item.price)*cart[item.id])}</span><div>${quantities(item)}</div></div></article>`).join('')}<div style="padding-top:22px">${routeLink('/menu/','← Continue browsing')}</div></div><aside class="order-summary"><h2>Your selection</h2><div class="summary-line"><span>Items (${Object.values(cart).reduce((a,b)=>a+b,0)})</span><span>${money(subtotal)}</span></div><div class="summary-line"><span>Delivery</span><span>Confirm on Annam</span></div><div class="summary-line summary-total"><span>Subtotal</span><span>${money(subtotal)}</span></div><a class="button" href="https://www.annamfood.in/" target="_blank" rel="noopener">Visit Annam to order ↗</a><p>This is a local preview cart. Your selection is saved on this browser only and won’t transfer to Annam’s website. No payment or order is processed here.</p></aside></div>`}</div>`;
  }
  function infoPage(slug) {
    const contents = {
      about: {title:'A taste of Annam.',intro:'Familiar South Indian flavours, from breakfast to celebration.',body:`${img(product('25-03-2023-saturday-idly-4'),'class="info-photo" width="500" height="500"')}<h2>Everyday meals. Traditional favourites.</h2><p>Annam Foods is based in Chennai. Its catalog brings together breakfast and lunch meals, sweets, savouries, podis and festive collections.</p><p>Explore the original dishes and photographs in this menu, from Idly with Vadai and Ghee Pongal to Tirunelveli Ghee Halwa and Thenkuzal.</p>${routeLink('/menu/','Explore the kitchen →','button')}`},
      'delivery-cashback': {title:'From our kitchen to you.',intro:'Find delivery information for your Annam order.',body:'<h2>Delivery depends on your order.</h2><p>Daily meals and packaged products have different delivery arrangements. Check the current availability and delivery details with Annam Foods before placing your order.</p><p>For the latest shipping timelines and charges, read the delivery information on the original website or contact the team.</p><a class="button" href="https://www.annamfood.in/shipping" target="_blank" rel="noopener">View Annam shipping information ↗</a><h2>Delivery cashback</h2><p>No cashback offer has been verified for this preview. Please check any current offers directly with Annam Foods.</p>'},
      'refund-policy': {title:'Help with your order.',intro:'Find the current refund policy and get in touch with Annam Foods.',body:'<h2>Read the current policy.</h2><p>For returns, refunds, missing items or product concerns, consult the official Annam Foods refund policy. The original website is the source for the terms that apply to your order.</p><a class="button" href="https://www.annamfood.in/refund-policy" target="_blank" rel="noopener">View Annam’s refund policy ↗</a><h2>Need a hand?</h2><p>Contact the Annam team with your order details and a description of your concern.</p>'}
    };
    const info = contents[slug] || contents.about;
    main.innerHTML = `<div class="wrap">${heading(info.title,info.intro,'Annam Foods')}<div class="info-layout"><div class="info-content">${info.body}</div><aside class="contact-card"><h3>We’re here to help.</h3><p>Annam Foods · Chennai</p><a href="tel:9551079550">95510 79550</a><a href="mailto:annamsfoods@gmail.com">annamsfoods@gmail.com</a>${routeLink('/menu/','Back to the menu →')}</aside></div></div>`;
  }
  function updateCount() { document.querySelector('#cart-count').textContent = Object.values(cart).reduce((a,b)=>a+b,0); }
  function showToast(message) { const toast=document.querySelector('#toast'); clearTimeout(toastTimer); toast.textContent=message; toast.classList.add('visible'); toastTimer=setTimeout(()=>toast.classList.remove('visible'),2600); }
  function changeCart(id, delta, remove = false) {
    const item = product(id); if (!item || !item.available) return;
    const next = remove ? 0 : Math.max(0,Math.min(20,(cart[id]||0)+delta));
    if (next) cart[id]=next; else delete cart[id];
    try { localStorage.setItem(storageKey,JSON.stringify(cart)); } catch { /* Session cart remains usable if storage is disabled. */ }
    updateCount();
    if (location.pathname==='/cart/') {
      cartPage();
      const target = next ? main.querySelector(`[data-id="${CSS.escape(id)}"][data-delta="${delta}"]`) : main.querySelector('.remove, .button');
      target?.focus({preventScroll:true});
    } else {
      document.querySelectorAll('[data-controls]').forEach(node=> { if(node.dataset.controls===id) node.innerHTML=quantities(item); });
      const target = main.querySelector(`[data-id="${CSS.escape(id)}"][data-delta="${delta}"]`) || main.querySelector(`[data-add="${CSS.escape(id)}"]`);
      target?.focus({preventScroll:true});
    }
    showToast(next ? `${item.name} · ${next} in your cart` : `${item.name} removed`);
  }
  function render(focus=false) {
    observer?.disconnect();
    const path=location.pathname;
    const nav=path==='/menu/'?'menu':path==='/cart/'?'cart':path==='/p/about/'?'about':path.startsWith('/p/')?'info':'home';
    document.querySelectorAll('[data-nav]').forEach(link=> { if(link.dataset.nav===nav) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current'); });
    if(path==='/menu/') menu(); else if(path==='/cart/') cartPage(); else if(path.startsWith('/p/')) infoPage(path.split('/')[2]); else home();
    document.title=(nav==='home'?'A taste of home':nav==='menu'?'Menu':nav==='cart'?'Your cart':'Information')+' · Annam Foods';
    main.classList.remove('page-enter'); void main.offsetWidth; main.classList.add('page-enter');
    observer=new IntersectionObserver(entries=>entries.forEach(entry=> { if(entry.isIntersecting){entry.target.classList.add('visible');observer.unobserve(entry.target);} }),{threshold:.08});
    main.querySelectorAll('.reveal').forEach(node=>observer.observe(node));
    if(focus) main.focus({preventScroll:true});
  }
  document.addEventListener('click', event=> {
    const link=event.target.closest('a[data-route]');
    if(link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button===0) { event.preventDefault(); history.pushState({},'',link.href); render(true); window.scrollTo(0,0); return; }
    const add=event.target.closest('[data-add]'); if(add){changeCart(add.dataset.add,1);return;}
    const delta=event.target.closest('[data-delta]'); if(delta){changeCart(delta.dataset.id,Number(delta.dataset.delta));return;}
    const remove=event.target.closest('[data-remove]'); if(remove){changeCart(remove.dataset.remove,0,true);return;}
    const filter=event.target.closest('[data-category]');
    if(filter){category=filter.dataset.category; const url=new URL(location.href); category==='all'?url.searchParams.delete('category'):url.searchParams.set('category',category);history.replaceState({},'',url);document.querySelectorAll('[data-category]').forEach(node=>node.setAttribute('aria-pressed',String(node.dataset.category===category)));renderResults();return;}
    if(event.target.closest('[data-reset]')){category='all';query='';document.querySelector('#search').value='';history.replaceState({},'','/menu/');document.querySelectorAll('[data-category]').forEach(node=>node.setAttribute('aria-pressed',String(node.dataset.category==='all')));renderResults();document.querySelector('#search').focus();}
  });
  document.addEventListener('input',event=>{if(event.target.id==='search'){query=event.target.value;renderResults();}});
  document.addEventListener('change',event=>{if(event.target.id==='sort'){sort=event.target.value;renderResults();}});
  window.addEventListener('popstate',()=>{if(catalog)render(true);});
  fetch('/static/annam-preview-catalog.json').then(response=>{if(!response.ok)throw Error('Catalog unavailable');return response.json();}).then(data=> {
    catalog=data;products=data.products;
    try { const saved=JSON.parse(localStorage.getItem(storageKey)||'{}'); for(const item of products){const qty=saved?.[item.id];if(item.available&&Number.isInteger(qty)&&qty>0&&qty<=20)cart[item.id]=qty;} } catch {cart={};}
    updateCount(); render();
  }).catch(()=> { main.innerHTML='<div class="wrap loading"><h1>The menu couldn’t load.</h1><p>Restart the preview server and refresh this page.</p></div>'; });
})();
