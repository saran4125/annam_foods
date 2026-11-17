(()=>{const root=document.querySelector('[data-receipt]');if(!root)return;
let timer;const poll=async()=>{try{const r=await fetch(root.dataset.statusUrl,{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;const s=await r.json();
document.querySelector('[data-order-status]').textContent=s.order_label;document.querySelector('[data-payment-status]').textContent=s.payment_label;
const view=root.querySelector('[data-invoice-view]'),download=root.querySelector('[data-invoice-download]');view.hidden=!s.invoice_url;if(s.invoice_url)view.href=s.invoice_url;download.hidden=!s.download_url;
if(s.download_url){download.href=s.download_url;download.textContent=s.test?'Download TEST receipt PDF':'Download invoice PDF';}
root.querySelector('[data-receipt-message]').textContent=s.test&&s.paid?'TEST / SIMULATED PAYMENT — NOT AN INVOICE':s.status==='refunded'?'Payment refunded. Contact the kitchen for help.':s.order_status==='cancelled'?'Order cancelled. Contact the kitchen about any payment made.':s.paid?(s.download_url?'Payment received. Your receipt is ready.':'Payment received. The kitchen is preparing your invoice.'):'Payment confirmation is pending.';
if(s.paid||s.status==='refunded'||s.order_status==='cancelled'){document.querySelectorAll('[data-payment-prompts]').forEach(f=>f.hidden=true);}
if(s.paid&&s.download_url){try{const key='receipt-download:'+root.dataset.reference;if(!sessionStorage.getItem(key)){sessionStorage.setItem(key,'1');download.click();}}catch{}}
}catch{}finally{timer=setTimeout(poll,5000);}};document.addEventListener('visibilitychange',()=>{if(!document.hidden){clearTimeout(timer);poll();}});poll();})();
