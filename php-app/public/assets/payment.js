document.querySelector('#pay-online')?.addEventListener('click',function(){
 const feedback=document.querySelector('[data-payment-feedback]');const say=text=>{if(feedback)feedback.textContent=text;};
 if(!window.Razorpay){say('Payment could not load. Please try again.');return;}
 const options=JSON.parse(this.dataset.options);options.modal={ondismiss:()=>say('Payment cancelled. Your order remains unpaid; retry when ready.')};
 options.handler=function(response){const form=document.querySelector('#payment-verify');for(const key of ['razorpay_payment_id','razorpay_order_id','razorpay_signature'])form.elements[key].value=response[key]||'';say('Verifying payment with the provider…');form.submit();};const checkout=new Razorpay(options);checkout.on('payment.failed',()=>say('Payment failed. Retry on this order or check its status.'));checkout.open();
});
