/* Native form fields remain authoritative; enhancement only rearranges rows. */
(() => {
  const list = document.querySelector('[data-section-list]');
  if (!list) return;
  const sync = () => {
    const rows = [...list.children];
    rows.forEach((row, index) => {
      row.querySelector('input[type=number]').value = index + 1;
      row.querySelector('.ap-section-number').textContent = String(index + 1).padStart(2, '0');
      row.querySelector('[data-move=up]').disabled = index === 0;
      row.querySelector('[data-move=down]').disabled = index === rows.length - 1;
    });
  };
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-move]');
    if (!button || button.disabled) return;
    const row = button.closest('[data-section-row]');
    const sibling = button.dataset.move === 'up' ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    if (button.dataset.move === 'up') list.insertBefore(row, sibling);
    else list.insertBefore(sibling, row);
    sync();
    row.scrollIntoView({ block: 'nearest' });
    if (button.disabled) row.querySelector('[data-move]:not(:disabled)')?.focus();
    else button.focus();
  });
  // Do not rewrite positions on load: a validation error must preserve inputs.
  const rows = [...list.children];
  rows[0]?.querySelector('[data-move=up]').setAttribute('disabled', '');
  rows.at(-1)?.querySelector('[data-move=down]').setAttribute('disabled', '');
  document.querySelectorAll('.ap-colour input').forEach(input => input.addEventListener('input', () => {
    input.closest('.ap-colour').querySelector('[data-colour-code]').textContent = input.value;
  }));
})();
