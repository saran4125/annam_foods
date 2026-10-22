/* Owner backend behaviour. Everything degrades: without JS every form still
   submits, every link still works. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Sidebar drawer on small screens */
  const side = $('[data-side]'), scrim = $('[data-scrim]'), burger = $('[data-burger]');
  const setNav = open => {
    if (!side) return;
    side.classList.toggle('is-open', open);
    burger?.setAttribute('aria-expanded', String(open));
    if (open) { scrim.hidden = false; requestAnimationFrame(() => scrim.classList.add('is-on')); }
    else { scrim.classList.remove('is-on'); setTimeout(() => { scrim.hidden = true; }, 250); }
  };
  burger?.addEventListener('click', () => setNav(!side.classList.contains('is-open')));
  scrim?.addEventListener('click', () => setNav(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') setNav(false); });

  /* Stagger index for entrance animation */
  $$('[data-stagger]').forEach(list => [...list.children].forEach((c, i) => c.style.setProperty('--i', Math.min(i, 12))));

  /* Filters apply as soon as they change */
  $$('select[data-autosubmit]').forEach(s => s.addEventListener('change', () => s.form.requestSubmit ? s.form.requestSubmit() : s.form.submit()));

  /* Packed shop products do not need a meal time or menu days. */
  const fulfilment = $('select[name="fulfilment"]');
  if (fulfilment) {
    const updateMealFields = () => $$('[data-meal-only]').forEach(field => { field.hidden = fulfilment.value !== 'scheduled'; });
    updateMealFields();
    fulfilment.addEventListener('change', updateMealFields);
  }

  /* Photo drop zones: drag-over state and instant preview */
  $$('[data-drop]').forEach(zone => {
    const input = $('input[type=file]', zone), preview = $('[data-preview]', zone);
    ['dragenter', 'dragover'].forEach(t => zone.addEventListener(t, e => { e.preventDefault(); zone.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(t => zone.addEventListener(t, () => zone.classList.remove('is-over')));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change')); }
    });
    input.addEventListener('change', () => {
      const file = input.files[0];
      if (!file || !preview) return;
      if (file.size > 5 * 1024 * 1024) { alert('That photo is over 5 MB. Please choose a smaller one.'); input.value = ''; return; }
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      preview.style.animation = 'none'; void preview.offsetWidth; preview.style.animation = '';
    });
  });

  /* Colour picker shows its hex value */
  $$('input[type=color]').forEach(input => {
    const code = input.parentElement.querySelector('[data-color-value]');
    input.addEventListener('input', () => { if (code) code.textContent = input.value; document.documentElement.style.setProperty('--brand', input.value); });
  });

  /* Success messages step aside after a few seconds; errors stay */
  $$('.o-flash:not(.o-flash-error)').forEach(f => setTimeout(() => {
    f.classList.add('is-gone');
    setTimeout(() => f.remove(), 300);
  }, 4000));

  /* Dashboard numbers count up once, on first view */
  if (!reduce) {
    $$('[data-count]').forEach(el => {
      const target = Number(el.dataset.count) || 0;
      if (target < 2) return;
      const start = performance.now(), dur = 700;
      const tick = now => {
        const t = Math.min((now - start) / dur, 1);
        el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
        if (t < 1) requestAnimationFrame(tick);
      };
      el.textContent = '0';
      requestAnimationFrame(tick);
    });
  }

  /* Login: show / hide the password (button only appears when JavaScript runs) */
  $$('[data-toggle-password]').forEach(btn => {
    const input = btn.parentElement.querySelector('[data-password]');
    btn.hidden = false;
    btn.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', String(show));
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      input.focus();
    });
  });
})();
