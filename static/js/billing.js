/* Meal-filtered item picker. Native selects remain the no-JavaScript fallback. */
(() => {
  'use strict';
  const catalogNode = document.getElementById('billing-catalog');
  if (!catalogNode) return;
  const catalog = JSON.parse(catalogNode.textContent);
  const areas = JSON.parse(document.getElementById('billing-delivery-areas').textContent);
  const items = new Map(catalog.map(item => [String(item.id), item]));
  const lines = document.getElementById('order-lines');
  const totalForms = document.getElementById('id_lines-TOTAL_FORMS');
  const money = value => new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR'}).format(value);
  const cents = value => Math.round(Number(value) * 100);
  const el = (tag, className, text) => { const node = document.createElement(tag); if(className) node.className=className; if(text!==undefined) node.textContent=text; return node; };
  function updateSummary() {
    let subtotal=0;
    const summary=document.getElementById('summary-items'); summary.replaceChildren();
    lines.querySelectorAll('[data-line]').forEach(row => {
      if(row.querySelector('[name$="-DELETE"]').checked) return;
      const item=items.get(row.querySelector('select').value);
      const qty=Number(row.querySelector('[name$="-quantity"]').value);
      const amount=item && Number.isInteger(qty) && qty>0 && qty<=999 ? cents(item.price)*qty : 0;
      row.querySelector('[data-line-total]').textContent=item ? money(amount/100) : '—';
      subtotal+=amount;
      if(item){const entry=el('div','b-summary-item');entry.append(el('span','',`${qty || 0} × ${item.name}`),el('strong','',money(amount/100)));summary.append(entry);}
    });
    if(!summary.children.length) summary.append(el('p','b-muted','Your selected items will appear here.'));
    const area=areas.find(a=>String(a.id)===document.getElementById('id_zone').value);
    const delivery=area?cents(area.fee):0;
    document.getElementById('summary-subtotal').textContent=money(subtotal/100);
    document.getElementById('summary-delivery').textContent=money(delivery/100);
    document.getElementById('summary-total').textContent=money((subtotal+delivery)/100);
    document.getElementById('minimum-note').textContent=area && subtotal<cents(area.minimum) ? `Add ${money((cents(area.minimum)-subtotal)/100)} to meet this area's minimum.` : '';
  }
  function setupRow(row) {
    const select=row.querySelector('select');
    const remove=row.querySelector('[name$="-DELETE"]');
    if(remove.checked){row.hidden=true;return;}
    const picker=el('details','b-picker');
    const trigger=el('summary','', 'Choose an item');
    const label=row.querySelector('label.b-label');
    trigger.id=`${select.id}-picker`; label.htmlFor=''; label.id=`${select.id}-label`; trigger.setAttribute('aria-labelledby',`${label.id} ${trigger.id}`);
    const panel=el('div','b-picker-panel');
    const search=el('input','o-input');search.type='search';search.placeholder='Search dishes or categories…';search.setAttribute('aria-label','Search items');
    const filters=el('div','b-meal-filters');filters.setAttribute('role','group');filters.setAttribute('aria-label','Meal filter');
    const options=el('div','b-picker-options');const count=el('p','b-picker-count');count.setAttribute('role','status');
    let group='all';
    const groupLabels=[['all','All'],['breakfast','Breakfast'],['lunch','Lunch'],['dinner','Dinner'],['other','Other items']];
    for(const [key,name] of groupLabels){const button=el('button','',name);button.type='button';button.dataset.group=key;button.addEventListener('click',()=>{group=key;render();});filters.append(button);}
    function render(){
      for(const b of filters.children) b.setAttribute('aria-pressed',String(b.dataset.group===group));
      const query=search.value.trim().toLocaleLowerCase();
      const matches=catalog.filter(item=>(group==='all'||item.groups.includes(group)) && `${item.name} ${item.category}`.toLocaleLowerCase().includes(query));
      options.replaceChildren();
      for(const item of matches){
        const button=el('button','b-picker-option');button.type='button';button.dataset.itemId=item.id;button.setAttribute('aria-pressed',String(String(item.id)===select.value));
        const description=el('span','',item.name);description.append(el('small','',item.category || item.groups.map(key=>groupLabels.find(pair=>pair[0]===key)[1]).join(' · ')));
        button.append(description,el('strong','',money(Number(item.price))));
        button.addEventListener('click',()=>{select.value=String(item.id);select.dispatchEvent(new Event('change',{bubbles:true}));picker.open=false;trigger.focus();});
        options.append(button);
      }
      if(!matches.length) options.append(el('p','b-muted','No items found. Try another meal or search.'));
      count.textContent=`${matches.length} item${matches.length===1?'':'s'}`;
    }
    function updateLabel(){const item=items.get(select.value);trigger.textContent=item?`${item.name} · ${money(Number(item.price))}`:'Choose an item';updateSummary();}
    select.addEventListener('change',updateLabel);
    search.addEventListener('input',render);
    search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();options.querySelector('button')?.focus();}if(event.key==='ArrowDown'){event.preventDefault();options.querySelector('button')?.focus();}});
    options.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;const buttons=[...options.querySelectorAll('button')];const i=buttons.indexOf(document.activeElement);const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,i+(event.key==='ArrowDown'?1:-1)));buttons[next]?.focus();event.preventDefault();});
    picker.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();picker.open=false;trigger.focus();}});
    picker.addEventListener('toggle',()=>{if(picker.open){document.querySelectorAll('.b-picker[open]').forEach(other=>{if(other!==picker)other.open=false;});render();search.focus();}});
    panel.append(search,filters,options,count);picker.append(trigger,panel);select.after(picker);select.hidden=true;select.required=false;
    const qty=row.querySelector('[name$="-quantity"]');qty.addEventListener('input',updateSummary);
    row.querySelectorAll('[data-step]').forEach(button=>button.addEventListener('click',()=>{qty.value=String(Math.max(1,Math.min(999,(Number(qty.value)||1)+Number(button.dataset.step))));updateSummary();}));
    const removeLabel=row.querySelector('.b-remove');
    const removeButton=el('button','b-remove','Remove');removeButton.type='button';removeButton.setAttribute('aria-label','Remove this item');
    removeLabel.hidden=true;removeLabel.after(removeButton);
    removeButton.addEventListener('click',()=>{
      remove.checked=true;row.hidden=true;select.disabled=true;qty.disabled=true;
      updateSummary();document.getElementById('add-line').focus();
    });
    updateLabel();
  }
  lines.querySelectorAll('[data-line]').forEach(setupRow);
  document.getElementById('add-line').addEventListener('click',event=>{
    event.stopPropagation();
    const n=Number(totalForms.value);
    if(n>=50){document.getElementById('line-limit').textContent='You can add up to 50 item rows.';return;}
    const fragment=document.getElementById('line-template').innerHTML.replace(/__prefix__/g,String(n));
    lines.insertAdjacentHTML('beforeend',fragment);totalForms.value=String(n+1);
    const row=lines.lastElementChild;setupRow(row);row.querySelector('details').open=true;
  });
  document.addEventListener('click',event=>{document.querySelectorAll('.b-picker[open]').forEach(picker=>{if(!picker.contains(event.target))picker.open=false;});});
  document.getElementById('id_zone').addEventListener('change',updateSummary);
  updateSummary();
})();
