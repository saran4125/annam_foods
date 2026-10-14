/* SeerKitchen storefront behaviour.
   Everything here is an enhancement: with JavaScript off, every page still
   renders fully and every form still submits normally. */
(() => {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  /* ---------- header: shadow once scrolled, mobile nav ------------------ */
  const header = $('[data-header]');
  if (header) {
    let ticking = false;
    const update = () => { header.classList.toggle('is-scrolled', window.scrollY > 8); ticking = false; };
    window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  const toggle = $('[data-nav-toggle]');
  const mobileNav = $('[data-mobile-nav]');
  if (toggle && mobileNav) {
    const setOpen = open => {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      mobileNav.hidden = !open;
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    window.matchMedia('(min-width: 860px)').addEventListener('change', e => { if (e.matches) setOpen(false); });
  }

  /* ---------- header search: a bar that opens under the header ---------- */
  const searchToggle = $('[data-search-toggle]');
  const searchPanel = $('[data-search-panel]');
  if (searchToggle && searchPanel) {
    const setSearch = open => {
      searchPanel.hidden = !open;
      searchToggle.setAttribute('aria-expanded', String(open));
      if (open) $('input', searchPanel).focus();
    };
    searchToggle.addEventListener('click', () => setSearch(searchPanel.hidden));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !searchPanel.hidden) { setSearch(false); searchToggle.focus(); }
    });
  }

  /* ---------- category row: arrows page by a screenful ------------------ */
  const shelfRow = $('[data-shelf-row]');
  if (shelfRow) {
    const wrap = shelfRow.closest('[data-shelf-wrap]');
    const prev = $('[data-shelf-prev]'), next = $('[data-shelf-next]');
    const sync = () => {
      const max = shelfRow.scrollWidth - shelfRow.clientWidth - 2;
      const atStart = shelfRow.scrollLeft <= 2, atEnd = shelfRow.scrollLeft >= max;
      wrap?.classList.toggle('has-prev', !atStart);
      wrap?.classList.toggle('has-next', !atEnd);
      if (prev) prev.disabled = atStart;
      if (next) next.disabled = atEnd;
    };
    const page = dir => {
      const from = shelfRow.scrollLeft, by = dir * shelfRow.clientWidth * 0.85;
      shelfRow.scrollBy({ left: by, behavior: reduceMotion ? 'auto' : 'smooth' });
      // Some browsers (and throttled tabs) drop smooth scrolling; never leave the arrow dead.
      setTimeout(() => { if (shelfRow.scrollLeft === from) shelfRow.scrollLeft = from + by; sync(); }, 450);
    };
    prev?.addEventListener('click', () => page(-1));
    next?.addEventListener('click', () => page(1));
    shelfRow.addEventListener('scroll', sync, { passive: true });  // cheap: two class toggles
    window.addEventListener('resize', sync);
    sync();
  }

  /* ---------- hero slider ----------------------------------------------- */
  const initSlider = root => {
    const slides = $$('[data-slide]', root);
    const dots = $$('[data-dot]', root);
    if (slides.length < 2) return;
    const interval = 5500;
    root.style.setProperty('--slide-ms', interval + 'ms');
    let current = 0;
    let timer = null;
    const autoplay = !reduceMotion;
    if (!autoplay) root.classList.add('no-autoplay');

    const show = index => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        const on = i === current;
        slide.classList.toggle('is-active', on);
        slide.setAttribute('aria-hidden', on ? 'false' : 'true');
        $('a', slide)?.setAttribute('tabindex', on ? '0' : '-1');
      });
      dots.forEach((dot, i) => {
        const on = i === current;
        // Re-adding the class restarts the progress-fill animation.
        dot.classList.remove('is-active');
        if (on) { void dot.offsetWidth; dot.classList.add('is-active'); }
        if (on) dot.setAttribute('aria-current', 'true'); else dot.removeAttribute('aria-current');
      });
    };
    const stop = () => { clearTimeout(timer); timer = null; };
    const schedule = () => {
      stop();
      if (autoplay) timer = setTimeout(() => { show(current + 1); schedule(); }, interval);
    };
    const go = index => { show(index); schedule(); };

    $('[data-prev]', root)?.addEventListener('click', () => go(current - 1));
    $('[data-next]', root)?.addEventListener('click', () => go(current + 1));
    dots.forEach(dot => dot.addEventListener('click', () => go(Number(dot.dataset.dot))));

    // Pause while the user is looking at / interacting with it, and offscreen.
    const pause = () => { root.classList.add('is-paused'); stop(); };
    const resume = () => { root.classList.remove('is-paused'); schedule(); };
    root.addEventListener('mouseenter', pause);
    root.addEventListener('mouseleave', resume);
    root.addEventListener('focusin', pause);
    root.addEventListener('focusout', resume);
    document.addEventListener('visibilitychange', () => (document.hidden ? pause() : resume()));

    // Swipe. Horizontal intent only, so vertical page scroll is never hijacked.
    let startX = 0, startY = 0, tracking = false;
    root.addEventListener('pointerdown', e => {
      if (e.pointerType === 'mouse' || e.target.closest('button')) return;
      startX = e.clientX; startY = e.clientY; tracking = true;
    });
    root.addEventListener('pointerup', e => {
      if (!tracking) return;
      tracking = false;
      const dx = e.clientX - startX, dy = e.clientY - startY;
      if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.4) go(current + (dx < 0 ? 1 : -1));
    });
    root.addEventListener('pointercancel', () => { tracking = false; });
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') go(current - 1);
      if (e.key === 'ArrowRight') go(current + 1);
    });

    show(0);
    schedule();
  };
  $$('[data-slider]').forEach(initSlider);

  /* ---------- scroll reveal (staggered children get an index) ----------- */
  const revealTargets = $$('[data-reveal],[data-stagger]');
  revealTargets.forEach(el => {
    if (el.hasAttribute('data-stagger')) [...el.children].forEach((child, i) => child.style.setProperty('--i', Math.min(i, 10)));
  });
  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealTargets.forEach(el => el.classList.add('is-in'));
  } else {
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.add('is-in'); io.unobserve(entry.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0 });  // 0: a long grid is never 8% visible
    revealTargets.forEach(el => io.observe(el));
  }

  /* ---------- images fade in once decoded ------------------------------- */
  const markLoaded = img => img.classList.add('is-loaded');
  const watchImages = (root = document) => {
    $$('.dish-media img, .food-photo img, .line-thumb img, .slot-cover img', root).forEach(img => {
      if (img.complete) markLoaded(img);
      else { img.addEventListener('load', () => markLoaded(img), { once: true }); img.addEventListener('error', () => markLoaded(img), { once: true }); }
    });
  };
  watchImages();

  /* ---------- hero: pointer parallax ------------------------------------
     Decorative mouse tracking on a marketing surface: fine pointers only,
     never under reduced motion. Each layer's transform is set directly and
     eased toward the target, so it settles instead of snapping. */
  const hero = $('[data-hero]');
  if (hero && !reduceMotion && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    const layers = $$('[data-depth]', hero).map(el => ({ el, depth: Number(el.dataset.depth) || 1, x: 0, y: 0 }));
    let tx = 0, ty = 0, raf = 0;
    const step = () => {
      let moving = false;
      layers.forEach(l => {
        const gx = tx * l.depth * 18, gy = ty * l.depth * 14;
        l.x += (gx - l.x) * 0.08; l.y += (gy - l.y) * 0.08;
        if (Math.abs(gx - l.x) > 0.05 || Math.abs(gy - l.y) > 0.05) moving = true;
        l.el.style.transform = `translate3d(${l.x.toFixed(2)}px, ${l.y.toFixed(2)}px, 0)`;
      });
      raf = moving ? requestAnimationFrame(step) : 0;
    };
    hero.addEventListener('pointermove', e => {
      const r = hero.getBoundingClientRect();
      tx = (e.clientX - r.left) / r.width - 0.5;
      ty = (e.clientY - r.top) / r.height - 0.5;
      if (!raf) raf = requestAnimationFrame(step);
    });
    hero.addEventListener('pointerleave', () => { tx = 0; ty = 0; if (!raf) raf = requestAnimationFrame(step); });
  }

  /* ---------- numbers count up once they scroll into view ---------------- */
  const counters = $$('[data-count-to]');
  if (counters.length && !reduceMotion && 'IntersectionObserver' in window) {
    const run = el => {
      const target = Number(el.dataset.countTo) || 0, start = performance.now(), dur = 1100;
      const tick = now => {
        const t = Math.min((now - start) / dur, 1);
        el.textContent = Math.round(target * (1 - Math.pow(1 - t, 4)));  // ease-out quart
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    const cio = new IntersectionObserver(entries => entries.forEach(en => {
      if (en.isIntersecting) { run(en.target); cio.unobserve(en.target); }
    }), { threshold: 0.6 });
    counters.forEach(el => { el.textContent = '0'; cio.observe(el); });
  }

  /* ---------- shop: re-sort as soon as the sort order changes ----------- */
  $$('select[data-autosubmit]').forEach(select => {
    select.addEventListener('change', () => select.form.requestSubmit ? select.form.requestSubmit() : select.form.submit());
  });

  /* ---------- toasts ---------------------------------------------------- */
  const toasts = $('[data-toasts]');
  const toast = (text, kind = 'ok') => {
    if (!toasts || !text) return;
    const el = document.createElement('div');
    el.className = 'toast' + (kind === 'error' ? ' is-error' : '');
    el.innerHTML = '<svg class="ic" aria-hidden="true"><use href="#i-' + (kind === 'error' ? 'close' : 'check') + '"/></svg><span></span>';
    $('span', el).textContent = text;
    toasts.appendChild(el);
    while (toasts.children.length > 3) toasts.firstElementChild.remove();
    setTimeout(() => {
      el.classList.add('is-leaving');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    }, 2600);
  };

  /* ---------- add to cart without a page reload -------------------------
     POST the form, follow the redirect, and patch only what changed from the
     page the server sends back. The server stays the authority on prices,
     stock and validity; any failure falls back to a normal form submit. */
  const patchFrom = (doc, form, wasBumpCandidate) => {
    // header cart pill
    const newLink = $('[data-cart-link]', doc);
    const oldLink = $('[data-cart-link]');
    if (newLink && oldLink) {
      const oldCount = $('[data-cart-count]', oldLink)?.textContent || '0';
      const newCount = $('[data-cart-count]', newLink)?.textContent || '0';
      oldLink.replaceWith(newLink);
      if (newCount !== oldCount && !reduceMotion) { newLink.classList.add('bump'); newLink.addEventListener('animationend', () => newLink.classList.remove('bump'), { once: true }); }
    }

    if (form.dataset.swap === 'main') {
      // Cart page: totals, minimums and line list all depend on each other.
      const scroll = window.scrollY;
      const newMain = $('#main', doc);
      if (newMain) {
        $('#main').innerHTML = newMain.innerHTML;
        // Already-cached thumbnails: show them at once instead of re-fading on every tap.
        $$('#main img').forEach(img => { img.style.transition = 'none'; markLoaded(img); });
      }
      window.scrollTo(0, scroll);
      return;
    }

    // Menu page: swap this dish's buy row, then the floating bar.
    const dish = form.closest('[data-item]');
    const newBuy = dish && $('[data-item="' + dish.dataset.item + '"] [data-buy]', doc);
    if (newBuy) {
      const buy = $('[data-buy]', dish);
      const oldQty = $('[data-qty]', buy)?.textContent;
      buy.innerHTML = newBuy.innerHTML;
      const qtyEl = $('[data-qty]', buy);
      if (qtyEl && qtyEl.textContent !== oldQty && !reduceMotion) qtyEl.classList.add('pop');
      $('button', buy)?.focus({ preventScroll: true });
    }
    const newBar = $('[data-cart-bar]', doc);
    const oldBar = $('[data-cart-bar]');
    if (newBar && oldBar) {
      const before = $('[data-bar-count]', oldBar).textContent;
      $('[data-bar-count]', oldBar).textContent = $('[data-bar-count]', newBar).textContent;
      oldBar.firstElementChild.lastChild.textContent = newBar.firstElementChild.lastChild.textContent;
      if (before !== $('[data-bar-count]', oldBar).textContent && !reduceMotion) {
        const b = $('[data-bar-count]', oldBar); b.classList.remove('pop'); void b.offsetWidth; b.classList.add('pop');
      }
    } else if (newBar && !oldBar) {
      $('#main').appendChild(newBar);
    } else if (!newBar && oldBar) {
      oldBar.remove();
    }
  };

  document.addEventListener('submit', async e => {
    const form = e.target.closest('form[data-cart-form]');
    if (!form || e.defaultPrevented || !window.fetch || !window.DOMParser) return;
    e.preventDefault();
    const submitter = e.submitter;
    const delta = submitter && submitter.name === 'delta' ? Number(submitter.value) : 1;
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);

    form.classList.add('is-busy');
    try {
      const res = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!res.ok) throw new Error('bad status');
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      const flashes = $$('[data-testid="flash"]', doc).map(f => f.textContent.trim());
      patchFrom(doc, form);
      if (flashes.length) flashes.forEach(t => toast(t, 'error'));
      else if (delta > 0 && form.dataset.name) toast('Added ' + form.dataset.name);
    } catch (err) {
      form.classList.remove('is-busy');
      // Fall back to a normal submit, keeping the clicked button's value.
      if (submitter && submitter.name) {
        const hidden = document.createElement('input');
        hidden.type = 'hidden'; hidden.name = submitter.name; hidden.value = submitter.value;
        form.appendChild(hidden);
      }
      HTMLFormElement.prototype.submit.call(form);
    }
  });
})();
