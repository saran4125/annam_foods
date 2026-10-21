/* A browser callback is a claim; the server verifies the signature and fetches capture. */
(()=>{
 const form=document.querySelector('#razorpay-payment');if(!form)return;
 const button=document.querySelector('[data-open-razorpay]'),feedback=document.querySelector('[data-payment-feedback]');
 const token=form.querySelector('[name=csrfmiddlewaretoken]').value;
 let busy=false,timer=null;
 const status=async()=>{const r=await fetch(form.dataset.statusUrl,{credentials:'same-origin'});if(!r.ok)throw Error();return r.json();};
 const poll=async(count=0)=>{try{const result=await status();if(result.paid || result.status==='refunded'){location.assign(form.dataset.completeUrl);return;}}catch{}if(count<10)timer=setTimeout(()=>poll(count+1),2500);else{feedback.textContent='Payment confirmation is still pending. Check your order status before trying again.';button.disabled=false;busy=false;}};
 button.addEventListener('click',()=>{
  if(busy)return;
  if(!window.Razorpay){feedback.textContent='Secure checkout could not load. Check your connection, then reload this page.';return;}
  busy=true;button.disabled=true;clearTimeout(timer);
  const options=JSON.parse(document.querySelector('#razorpay-options').textContent);
  options.handler=async result=>{
   feedback.textContent='Verifying your payment…';
   try{const data=new URLSearchParams({...result,csrfmiddlewaretoken:token});const r=await fetch(form.dataset.verifyUrl,{method:'POST',body:data,credentials:'same-origin'});const body=await r.json();if(r.ok && body.paid){location.assign(form.dataset.completeUrl);return;}feedback.textContent=body.error || 'Awaiting payment capture. We are checking with Razorpay.';}catch{feedback.textContent='Confirmation is pending. Please check your order before retrying.';}
   poll();
  };
  options.modal={ondismiss:()=>{feedback.textContent='Checkout closed. Your order is saved; check its payment status before retrying.';busy=false;button.disabled=false;}};
  try{const checkout=new Razorpay(options);
  checkout.on('payment.failed',()=>{feedback.textContent='Payment did not complete. You can retry on this order.';busy=false;button.disabled=false;});
  checkout.open();}catch{feedback.textContent='Secure checkout could not open. Reload this page and try again.';busy=false;button.disabled=false;}
 });
})();
