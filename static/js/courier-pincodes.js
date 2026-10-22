/* Enhance the existing textarea; its name and server validation stay unchanged. */
(() => {
  'use strict';
  const editor = document.querySelector('[data-pincode-editor]');
  if (!editor) return;
  const source = editor.querySelector('textarea');
  const sheet = editor.querySelector('[data-pincode-sheet]');
  const body = editor.querySelector('[data-pincode-rows]');
  const status = editor.querySelector('[data-pincode-status]');
  const limit = 10000;
  const inputs = () => [...body.querySelectorAll('input')];
  function sync() {
    const fields = inputs();
    const values = fields.map(field => field.value.trim()).filter(Boolean);
    source.value = values.join('\n');
    fields.forEach((field, index) => {
      field.setAttribute('aria-label', `Delivery pincode, row ${index + 1}`);
      field.closest('tr').querySelector('th').textContent = index + 1;
      const invalid = field.value.trim() && !/^[1-9][0-9]{5}$/.test(field.value.trim());
      field.setAttribute('aria-invalid', String(Boolean(invalid)));
      field.closest('tr').querySelector('button').setAttribute('aria-label', `Remove row ${index + 1}`);
    });
    const invalid = fields.some(field => field.getAttribute('aria-invalid') === 'true');
    const duplicate = values.length !== new Set(values).size;
    status.textContent = `${new Set(values).size} unique pincode${new Set(values).size === 1 ? '' : 's'}`
      + (invalid ? ' · Check highlighted cells: use exactly six digits.' : '')
      + (duplicate ? ' · Duplicate pincodes are saved once.' : '');
  }
  function add(value = '', before = null) {
    const row = document.createElement('tr');
    const number = document.createElement('th');
    number.scope = 'row';
    const cell = document.createElement('td');
    const field = document.createElement('input');
    field.type = 'text';
    field.inputMode = 'numeric';
    field.autocomplete = 'off';
    field.placeholder = 'e.g. 600005';
    field.setAttribute('aria-describedby', 'pincode-help');
    field.value = value;
    cell.append(field);
    const action = document.createElement('td');
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'o-btn o-danger-btn';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => {
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      if (!body.children.length) add();
      sync();
      (next || body.firstElementChild).querySelector('input').focus();
    });
    action.append(remove);
    row.append(number, cell, action);
    body.insertBefore(row, before);
    return field;
  }
  const initial = source.value.trim().split(/\s+/).filter(Boolean);
  (initial.length ? initial : ['']).forEach(value => add(value));
  editor.querySelector('[data-pincode-add]').addEventListener('click', () => {
    if (body.children.length >= limit) { status.textContent = 'Maximum 10,000 rows. Remove a row before adding another.'; return; }
    const field = add();
    sync();
    field.focus();
  });
  body.addEventListener('input', sync);
  body.addEventListener('paste', event => {
    if (!event.target.matches('input')) return;
    const text = event.clipboardData.getData('text/plain');
    if (!/[\r\n\t]/.test(text)) return;
    event.preventDefault();
    const lines = text.trim().split(/\r\n|\n|\r/).filter(line => line.trim());
    if (lines.some(line => line.includes('\t'))) {
      status.textContent = 'Paste only the pincode column, without other columns or a heading.';
      return;
    }
    if (body.children.length + lines.length - 1 > limit) {
      status.textContent = 'Maximum 10,000 rows. Paste fewer pincodes.';
      return;
    }
    if (!lines.length) return;
    event.target.value = lines[0].trim();
    const before = event.target.closest('tr').nextElementSibling;
    lines.slice(1).forEach(line => add(line.trim(), before));
    sync();
  });
  source.form.addEventListener('submit', sync);
  editor.querySelector('[data-pincode-fallback]').hidden = true;
  sheet.hidden = false;
  sync();
})();
