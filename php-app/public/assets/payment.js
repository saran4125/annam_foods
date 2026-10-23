document.querySelector('#pay-online')?.addEventListener('click',function(){
 if(!window.Razorpay){alert('Payment could not load. Please try again.');return;}
 const options=JSON.parse(this.dataset.options);options.handler=function(response){const form=document.querySelector('#payment-verify');for(const key of ['razorpay_payment_id','razorpay_order_id','razorpay_signature'])form.elements[key].value=response[key]||'';form.submit();};new Razorpay(options).open();
});
