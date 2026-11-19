/* Progressive enhancement for PHP forms using the Python UI components. */
(()=>{'use strict';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const toggle=(button,panel)=>{if(!button||!panel)return;const close=()=>{panel.hidden=true;button.setAttribute('aria-expanded','false');};button.addEventListener('click',()=>{panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)$('input',panel)?.focus();});document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});};
toggle($('[data-nav-toggle]'),$('[data-mobile-nav]'));toggle($('[data-search-toggle]'),$('[data-search-panel]'));
$$('[data-slider]').forEach(slider=>{const slides=$$('[data-slide]',slider),dots=$$('[data-dot]',slider);let current=0;const show=n=>{current=(n+slides.length)%slides.length;slides.forEach((slide,i)=>{slide.classList.toggle('is-active',i===current);slide.setAttribute('aria-hidden',String(i!==current));$$('a,button',slide).forEach(el=>el.tabIndex=i===current?0:-1);});dots.forEach((dot,i)=>{dot.classList.toggle('is-active',i===current);dot.setAttribute('aria-pressed',String(i===current));});};$('[data-prev]',slider)?.addEventListener('click',()=>show(current-1));$('[data-next]',slider)?.addEventListener('click',()=>show(current+1));dots.forEach((dot,i)=>dot.addEventListener('click',()=>show(i)));if(slides.length)show(0);});
$$('[data-public-autosubmit]').forEach(el=>el.addEventListener('change',()=>el.form.requestSubmit()));
const password=$('[data-login-password]');$('[data-password-toggle]')?.addEventListener('click',e=>{const visible=password.type==='password';password.type=visible?'text':'password';e.currentTarget.setAttribute('aria-pressed',String(visible));e.currentTarget.setAttribute('aria-label',visible?'Hide password':'Show password');});
})();
/* Cart changes are priced and validated by PHP; forms still work without JS. */
(()=>{'use strict';
const all=(s,r=document)=>[...r.querySelectorAll(s)];
const toast=(message,error=false)=>{const box=document.querySelector('[data-toasts]');if(!box)return;const el=document.createElement('div');el.className='toast'+(error?' is-error':'');el.textContent=message;box.append(el);setTimeout(()=>el.remove(),4500);};
const controls=(form,n)=>{const root=form.querySelector('[data-cart-controls]');if(!root)return;root.replaceChildren();if(!n){const add=document.createElement('button');add.className='btn btn-add';add.name='delta';add.value='1';add.textContent='Add';root.append(add);return;}const group=document.createElement('span');group.className='stepper';group.setAttribute('role','group');group.setAttribute('aria-label',form.dataset.name+' quantity');[-1,1].forEach((delta,i)=>{if(i){const count=document.createElement('span');count.dataset.qty='';count.textContent=n;group.append(count);}const button=document.createElement('button');button.name='delta';button.value=delta;button.textContent=i?'+':'−';button.setAttribute('aria-label',(i?'One more ':'One fewer ')+form.dataset.name);group.append(button);});root.append(group);};
let updating=false;
document.addEventListener('submit',async e=>{const form=e.target;if(!form.matches('[data-cart-form]'))return;e.preventDefault();if(updating)return;updating=true;form.setAttribute('aria-busy','true');const body=new FormData(form);if(e.submitter?.name)body.set(e.submitter.name,e.submitter.value);try{const response=await fetch(form.action,{method:'POST',body,headers:{'X-Requested-With':'fetch'},credentials:'same-origin'});const type=response.headers.get('Content-Type')||'';if(!type.includes('application/json'))throw Error('Please refresh the page and try again.');const data=await response.json();if(!response.ok)throw Error(data.error||'Unable to update your cart.');const id=form.querySelector('[name=item_id]').value,slot=form.querySelector('[name=slot_id]')?.value,date=form.querySelector('[name=date]')?.value;all('[data-cart-form]').filter(f=>f.querySelector('[name=item_id]').value===id&&f.querySelector('[name=slot_id]')?.value===slot&&f.querySelector('[name=date]')?.value===date).forEach(f=>controls(f,data.quantity));all('[data-cart-count]').forEach(el=>{el.textContent=data.count;el.hidden=!data.count;});const bar=document.querySelector('[data-cart-bar]');if(bar)bar.hidden=!data.count;all('[data-bar-count]').forEach(el=>el.textContent=data.count);all('[data-cart-subtotal]').forEach(el=>el.textContent=data.subtotal);toast(data.quantity?form.dataset.name+' · '+data.quantity+' in cart':'Removed from your cart');}catch(error){toast(error.message,true);}finally{updating=false;form.removeAttribute('aria-busy');}});
all('[data-shelf-wrap]').forEach(wrap=>{const row=wrap.querySelector('[data-shelf-row]'),prev=wrap.querySelector('[data-shelf-prev]'),next=wrap.querySelector('[data-shelf-next]');if(!row||!prev||!next)return;const state=()=>{prev.disabled=row.scrollLeft<2;next.disabled=row.scrollLeft+row.clientWidth>=row.scrollWidth-2;};prev.addEventListener('click',()=>row.scrollBy({left:-row.clientWidth*.8,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));next.addEventListener('click',()=>row.scrollBy({left:row.clientWidth*.8,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));row.addEventListener('scroll',state,{passive:true});window.addEventListener('resize',state);state();});
const head=document.querySelector('[data-header]');if(head){const state=()=>{if(window.scrollY>96)head.classList.add('is-scrolled');else if(window.scrollY<24)head.classList.remove('is-scrolled');};window.addEventListener('scroll',state,{passive:true});state();}
})();

(()=>{
  /* Check delivery in place; never navigate away from the cart. Requests are
     serialized so an older pincode cannot overwrite the latest session value. */
  let pincodeTimer, checkingPincode = false, pendingPincode = false;
  const pincodeForm = () => document.querySelector('[data-pincode-form]');
  const pincodeSignature = form => form.elements.pincode.value + ':' + (form.elements.area_id?.value || '');
  const lockDelivery = message => {
    const form = pincodeForm();
    const side = form?.closest('[data-pincode-side]');
    const feedback = side?.querySelector('[data-pincode-feedback]');
    if (feedback) feedback.textContent = message;
    side?.querySelectorAll('.php-success').forEach(el => el.hidden = true);
    const checkout = side?.querySelector('[data-testid="checkout"]');
    if (checkout) { checkout.setAttribute('aria-disabled', 'true'); if (checkout.tagName === 'BUTTON') checkout.disabled = true; }
  };
  document.addEventListener('click', event => {
    if (event.target.closest('[data-testid="checkout"][aria-disabled="true"]')) event.preventDefault();
  });
  const checkPincode = async () => {
    clearTimeout(pincodeTimer);
    const form = pincodeForm();
    if (!form || !/^[1-9][0-9]{5}$/.test(form.elements.pincode.value)) return;
    pendingPincode = true;
    if (checkingPincode) return;
    checkingPincode = true;
    while (pendingPincode) {
      pendingPincode = false;
      const current = pincodeForm();
      if (!current || !/^[1-9][0-9]{5}$/.test(current.elements.pincode.value)) break;
      const signature = pincodeSignature(current);
      lockDelivery('Checking delivery…');
      try {
        const response = await fetch(current.action, {method: 'POST', body: new FormData(current), credentials: 'same-origin'});
        if (!response.ok) throw new Error('Delivery check failed');
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const next = doc.querySelector('[data-pincode-side]');
        if (!next?.querySelector('[data-pincode-form]')) throw new Error('Invalid delivery response');
        const live = pincodeForm();
        if (!live || pincodeSignature(live) !== signature) continue;
        const focused = document.activeElement === live.elements.pincode;
        live.closest('[data-pincode-side]').replaceWith(next);
        const feedback = next.querySelector('[data-pincode-feedback]');
        const errors = [...next.querySelectorAll('.php-error')].map(el => el.textContent.trim());
        if (feedback && errors.length) lockDelivery(errors.join(' '));
        if (focused) next.querySelector('[name="pincode"]').focus({preventScroll: true});
      } catch {
        if (pincodeForm() && pincodeSignature(pincodeForm()) === signature) lockDelivery('Could not check delivery. Please try Check again.');
      }
    }
    checkingPincode = false;
  };
  document.addEventListener('input', event => {
    if (!event.target.matches('[data-pincode-form] [name="pincode"]')) return;
    clearTimeout(pincodeTimer);
    const form = event.target.form;
    const area = form.elements.area_id;
    if (area) area.value = '';
    lockDelivery(/^[1-9][0-9]{5}$/.test(event.target.value) ? 'Checking delivery…' : 'Enter a complete 6-digit pincode.');
    if (/^[1-9][0-9]{5}$/.test(event.target.value)) pincodeTimer = setTimeout(checkPincode, 350);
  });
  document.addEventListener('change', event => {
    if (event.target.matches('[data-pincode-form] select[name="area_id"]')) checkPincode();
  });
  document.addEventListener('submit', event => {
    if (!event.target.matches('[data-pincode-form]') || !window.fetch) return;
    event.preventDefault(); checkPincode();
  });


})();

// Confirm reversible removal actions before submitting.
document.addEventListener('submit',event=>{const form=event.target;if(form.matches('form[data-confirm]')&&!confirm(form.dataset.confirm))event.preventDefault();});
