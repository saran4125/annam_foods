/* Area choices and estimates come from the scoped server delivery service. */
(()=>{'use strict';
 const form=document.querySelector('[data-checkout-delivery]');if(!form)return;
 const pin=form.elements.pincode,country=form.elements.country,select=form.elements.zone_id,field=form.querySelector('[data-checkout-area]'),feedback=form.querySelector('[data-delivery-feedback]'),fee=document.querySelector('[data-delivery-fee]'),total=document.querySelector('[data-delivery-total]'),button=document.querySelector('button[form="delivery-details"]');
 const paymentAvailable=form.elements.payment_method.options.length>0;
 const money=n=>'₹'+(n/100).toLocaleString('en-IN',{minimumFractionDigits:n%100?2:0,maximumFractionDigits:2});
 let timer,controller;
 const reset=()=>{field.hidden=true;select.required=false;select.disabled=true;select.replaceChildren(new Option('Choose your area',''));fee.textContent='Enter pincode / choose area';total.textContent='Confirmed at review';};
 async function check(){
  clearTimeout(timer);controller?.abort();const signature=pin.value.trim()+':'+country.value.trim()+':'+select.value;
  if((country.value.trim().toLowerCase()==='india'||form.dataset.mealDelivery==='1')&&!/^[1-9][0-9]{5}$/.test(pin.value.trim())){reset();feedback.textContent='Enter a valid 6-digit pincode.';button.disabled=true;return;}
  controller=new AbortController();button.disabled=true;feedback.textContent='Checking delivery…';
  try{
   const params=new URLSearchParams({pincode:pin.value.trim(),country:country.value.trim(),zone_id:select.value});
   const response=await fetch('/checkout/delivery/?'+params,{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)throw Error();const data=await response.json();
   if(signature!==pin.value.trim()+':'+country.value.trim()+':'+select.value)return;
   const previous=select.value;select.replaceChildren(new Option('Choose your area',''));
   data.areas.forEach(area=>select.add(new Option(area.name+' — '+money(area.fee)+' delivery',String(area.id))));
   select.disabled=!data.areas.length;select.required=data.areas.length>1;field.hidden=data.areas.length<=1;
   select.value=data.selected!==null?String(data.selected):(data.areas.some(area=>String(area.id)===previous)?previous:'');
   fee.textContent=data.fee!==null?money(data.fee):(data.areas.length?'Choose your area':'Confirmed at review');total.textContent=data.fee!==null?money(data.subtotal+data.fee):money(data.subtotal);
   feedback.textContent=data.error||(data.fee!==null?'Delivery charge updated for your area.':'Courier delivery is confirmed at review.');button.disabled=!paymentAvailable||!data.eligible;
  }catch(error){if(error.name==='AbortError')return;feedback.textContent='Could not check delivery. You can review the order to check your pincode and area.';button.disabled=!paymentAvailable;}
 }
 pin.addEventListener('input',()=>{reset();button.disabled=true;feedback.textContent='';clearTimeout(timer);controller?.abort();timer=setTimeout(check,350);});
 country.addEventListener('change',()=>{reset();check();});select.addEventListener('change',check);
 if(pin.value.trim())check();
})();
