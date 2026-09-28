document.querySelectorAll('[data-seer-slider]').forEach(root => {
  const slides = [...root.querySelectorAll('[data-seer-slide]')];
  const dots = [...root.querySelectorAll('[data-seer-dot]')];
  if (slides.length < 2) return;
  let index = 0, timer, paused = false;
  const show = next => {
    index = (next + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.classList.toggle('is-active', i === index);
      slide.setAttribute('aria-hidden', i === index ? 'false' : 'true');
      slide.querySelectorAll('a').forEach(link => link.tabIndex = i === index ? 0 : -1);
    });
    dots.forEach((dot, i) => dot.setAttribute('aria-pressed', String(i === index)));
  };
  const stop = () => clearInterval(timer);
  const start = () => {
    stop();
    if (!paused && !matchMedia('(prefers-reduced-motion: reduce)').matches && !root.contains(document.activeElement) && !document.hidden) timer = setInterval(() => show(index + 1), 6000);
  };
  root.querySelector('.seer-pause').addEventListener('click', event => { paused = !paused; event.currentTarget.setAttribute('aria-pressed', String(paused)); event.currentTarget.setAttribute('aria-label', paused ? 'Play slideshow' : 'Pause slideshow'); event.currentTarget.textContent = paused ? 'Play' : 'Pause'; paused ? stop() : start(); });
  root.querySelector('.seer-prev').addEventListener('click', () => { stop(); show(index - 1); });
  root.querySelector('.seer-next').addEventListener('click', () => { stop(); show(index + 1); });
  dots.forEach((dot, i) => dot.addEventListener('click', () => { stop(); show(i); }));
  root.addEventListener('mouseenter', stop);
  root.addEventListener('mouseleave', start);
  root.addEventListener('focusin', stop);
  root.addEventListener('focusout', start);
  root.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { stop(); show(index + (event.key === 'ArrowRight' ? 1 : -1)); }
  });
  document.addEventListener('visibilitychange', () => document.hidden ? stop() : start());
  show(0); start();
});
