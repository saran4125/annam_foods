/* Staff-only phone lookup; saved values remain editable and late replies cannot undo typing. */
(() => {
  'use strict';
  const form = document.getElementById('booking-form');
  if (!form?.dataset.customerLookup) return;
  const phone = form.elements.phone;
  const status = document.getElementById('customer-lookup-status');
  const fields = ['name', 'address', 'city', 'state', 'country', 'postal_code', 'zone', 'fulfilment_method'];
  let timer, controller, revision = 0, lastKey = '', filled = {};
  function key() {
    const digits = phone.value.replace(/[\s()+-]/g, '');
    return digits.length === 12 && digits.startsWith('91') ? digits.slice(2) : digits;
  }
  function clearPrevious() {
    for (const [name, value] of Object.entries(filled)) {
      const field = form.elements[name];
      if (field.value === value) {
        field.value = name === 'state' ? 'Tamil Nadu' : name === 'country' ? 'India' : '';
        field.dispatchEvent(new Event('change', {bubbles:true}));
      }
    }
    filled = {};
  }
  async function lookup(version) {
    const currentKey = key();
    if (version !== revision || !/^[0-9]{10,15}$/.test(currentKey) || currentKey === lastKey) return;
    lastKey = currentKey;
    controller = new AbortController();
    const before = Object.fromEntries(fields.map(name => [name, form.elements[name].value]));
    status.textContent = 'Looking for saved customer details…';
    try {
      const url = new URL(form.dataset.customerLookup, location.origin);
      url.searchParams.set('phone', phone.value);
      const response = await fetch(url, {signal:controller.signal, cache:'no-store', headers:{Accept:'application/json'}});
      if (!response.ok) throw new Error('Lookup unavailable');
      const result = await response.json();
      if (version !== revision || key() !== currentKey) return;
      if (!result.found) {
        status.textContent = 'New customer. Enter their name and delivery details below.';
        return;
      }
      for (const name of fields) {
        const field = form.elements[name];
        if (field.value !== before[name]) continue; // Staff edited this field while lookup was pending.
        field.value = result.details[name] ?? '';
        filled[name] = field.value;
        field.dispatchEvent(new Event('change', {bubbles:true}));
      }
      status.textContent = result.needs_area_selection
        ? 'Saved details filled. Select the current delivery area and review the address. You can edit all details.'
        : 'Saved customer details filled. Review the name and address; you can edit all details.';
    } catch (error) {
      if (error.name === 'AbortError' || version !== revision) return;
      lastKey = '';
      status.textContent = 'Saved details could not be loaded. Enter them manually, or leave the phone field to retry.';
    }
  }
  phone.addEventListener('input', () => {
    clearTimeout(timer);
    if (key() === lastKey) return;
    controller?.abort();
    revision++;
    lastKey = '';
    clearPrevious();
    status.textContent = 'Enter a phone number to find saved customer details.';
    const version = revision;
    timer = setTimeout(() => lookup(version), 450);
  });
  phone.addEventListener('blur', () => {clearTimeout(timer); lookup(revision);});
  if (form.dataset.lookupInitial === 'true' && phone.value) lookup(revision);
})();
