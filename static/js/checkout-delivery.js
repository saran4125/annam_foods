/* Area choices and estimates come from the scoped server delivery service. */
(()=>{'use strict';
 const form=document.querySelector('[data-checkout-delivery]');if(!form)return;
 const pin=form.elements.pincode,country=form.elements.country,select=form.elements.zone_id,field=form.querySelector('[data-checkout-area]'),feedback=form.querySelector('[data-delivery-feedback]'),fee=document.querySelector('[data-delivery-fee]'),total=document.querySelector('[data-delivery-total]'),button=document.querySelector('button[form="delivery-details"]');
 const paymentAvailable=form.elements.payment_method.options.length>0;
 const money=n=>'₹'+(n/100).toLocaleString('en-IN',{minimumFractionDigits:n%100?2:0,maximumFractionDigits:2});
 let timer,controller,addressController,addressPin=pin.value.trim(),sequence=0;
 const addressFields=['line1','line2','city','landmark','state'];
 const addressFeedback=form.querySelector('[data-address-feedback]');
 async function restoreAddress(){
  addressController?.abort();const value=pin.value.trim(),region=country.value.trim();
  if(!/^[1-9][0-9]{5}$/.test(value)||region.toLowerCase()!=='india')return;
  const captured=Object.fromEntries([...addressFields,'name','phone','email'].map(key=>[key,form.elements[key].value]));
  addressController=new AbortController();
  try{const response=await fetch('/checkout/address/?'+new URLSearchParams({pincode:value,country:region}),{credentials:'same-origin',cache:'no-store',signal:addressController.signal});if(!response.ok)throw Error();const data=await response.json();
   if(pin.value.trim()!==value||country.value.trim()!==region)return;
   addressPin=value;
   if(data.address){for(const key of [...addressFields,'name','phone','email']){const input=form.elements[key];if(input.value===captured[key]&&(addressFields.includes(key)||!input.value))input.value=data.address[key]||'';}addressFeedback.textContent='Saved address filled for this pincode. You can edit it below.';}
   else addressFeedback.textContent='Enter your address for this pincode. It will be remembered after you place the order.';
  }catch(error){if(error.name!=='AbortError')addressFeedback.textContent='Enter your delivery address below.';}
 }
 const clearAddress=()=>{addressController?.abort();if(addressPin!==null){for(const key of addressFields)form.elements[key].value=key==='state'?'Tamil Nadu':'';addressPin=null;}addressFeedback.textContent='';};
 const reset=()=>{field.hidden=true;select.required=false;select.disabled=true;select.replaceChildren(new Option('Choose your area',''));fee.textContent='Enter pincode / choose area';total.textContent='Confirmed at review';};
 async function check(){
  clearTimeout(timer);controller?.abort();const request=++sequence;const signature=pin.value.trim()+':'+country.value.trim()+':'+select.value;
  if((country.value.trim().toLowerCase()==='india'||form.dataset.mealDelivery==='1')&&!/^[1-9][0-9]{5}$/.test(pin.value.trim())){reset();feedback.textContent='Enter a valid 6-digit pincode.';button.disabled=true;return;}
  controller=new AbortController();button.disabled=true;feedback.textContent='Checking delivery…';
  try{
   const params=new URLSearchParams({pincode:pin.value.trim(),country:country.value.trim(),zone_id:select.value});
   const response=await fetch('/checkout/delivery/?'+params,{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)throw Error();const data=await response.json();
   if(request!==sequence||signature!==pin.value.trim()+':'+country.value.trim()+':'+select.value)return;
   const previous=select.value;select.replaceChildren(new Option('Choose your area',''));
   data.areas.forEach(area=>select.add(new Option(area.name+' — '+money(area.fee)+' delivery',String(area.id))));
   select.disabled=!data.areas.length;select.required=data.areas.length>1;field.hidden=data.areas.length<=1;
   select.value=data.selected!==null?String(data.selected):(data.areas.some(area=>String(area.id)===previous)?previous:'');
   fee.textContent=data.fee!==null?money(data.fee):(data.areas.length?'Choose your area':'Confirmed at review');total.textContent=data.fee!==null?money(data.subtotal+data.fee):money(data.subtotal);
   feedback.textContent=data.error||(data.fee!==null?'Delivery charge updated for your area.':'Courier delivery is confirmed at review.');button.disabled=!paymentAvailable||!data.eligible;
  }catch(error){if(error.name==='AbortError'||request!==sequence)return;reset();feedback.textContent='Could not check delivery. Try again before continuing.';button.disabled=true;}
 }
 pin.addEventListener('input',()=>{++sequence;clearAddress();reset();button.disabled=true;feedback.textContent='';clearTimeout(timer);controller?.abort();timer=setTimeout(()=>{restoreAddress();check();},350);});
 country.addEventListener('change',()=>{++sequence;clearAddress();reset();restoreAddress();check();});select.addEventListener('change',check);
 form.addEventListener('submit',event=>{if(button.disabled){event.preventDefault();feedback.textContent='Check your delivery pincode and area before continuing.';}});
 if(pin.value.trim())check();
})();
