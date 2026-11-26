/* Export the actual copied receipt DOM, so browser downloads use the print design. */
(()=>{
  const scriptURL=document.currentScript?.src||location.href;
  const libraryURL=document.currentScript?.dataset.pdfLibrary||new URL('html2pdf-0.14.0.bundle.min.js',scriptURL).href;
  let exporting=false;
  document.addEventListener('click',async event=>{
    const link=event.target.closest('a[data-pdf-source],a[data-invoice-download]');
    if(!link||link.hidden||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    const source=link.dataset.pdfSource||link.closest('[data-receipt]')?.querySelector('[data-invoice-view]:not([hidden])')?.getAttribute('href');
    if(!source)return;const url=new URL(source,location.href);if(url.origin!==location.origin)return;
    event.preventDefault();if(exporting)return;exporting=true;
    const nativeURL=link.href;link.setAttribute('aria-busy','true');
    const frame=document.createElement('iframe');frame.setAttribute('aria-hidden','true');frame.tabIndex=-1;
    Object.assign(frame.style,{position:'fixed',left:'-10000px',top:'0',width:'794px',height:'1123px',border:'0'});
    try{
      const response=await fetch(url.href,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('Receipt unavailable');
      const parsed=new DOMParser().parseFromString(await response.text(),'text/html'),sourceReceipt=parsed.querySelector('.af-receipt');if(!sourceReceipt)throw Error('Receipt unavailable');
      const css=[...parsed.querySelectorAll('link[rel="stylesheet"]')].filter(link=>{const href=new URL(link.getAttribute('href'),url);return href.origin===location.origin&&/\/receipt(?:\.[a-f0-9]+)?\.css$/i.test(href.pathname);}).map(link=>link.outerHTML).join('');
      const loaded=new Promise((resolve,reject)=>{frame.onload=resolve;frame.onerror=reject;});frame.srcdoc='<!doctype html><html><head><meta charset="utf-8">'+css+'</head><body>'+sourceReceipt.outerHTML+'</body></html>';document.body.append(frame);await loaded;
      const doc=frame.contentDocument,win=frame.contentWindow,receipt=doc.querySelector('.af-receipt');if(!receipt)throw Error('Receipt unavailable');
      // Apply the original main-branch print rules without duplicating or restyling them.
      const printRules=[];for(const sheet of doc.styleSheets){try{for(const rule of sheet.cssRules){if(rule.type===4&&rule.conditionText==='print')for(const child of rule.cssRules)if(child.type!==6)printRules.push(child.cssText);}}catch{}}
      const style=doc.createElement('style');style.textContent=printRules.join('\n')+'\nhtml,body{margin:0!important;padding:0!important}.bill-actions{display:none!important}';doc.head.append(style);
      await doc.fonts.ready;await Promise.all([...receipt.querySelectorAll('img')].map(img=>img.decode()));
      await new Promise((resolve,reject)=>{const library=doc.createElement('script');library.src=libraryURL;library.onload=resolve;library.onerror=reject;doc.head.append(library);});
      const number=receipt.querySelector('.af-receipt-meta dd')?.textContent.trim();
      const filename=link.dataset.pdfFilename||(number?number.replace(/[^a-z0-9._-]/gi,'-')+'.pdf':'invoice.pdf');
      const options=win.JSON.parse(JSON.stringify({filename,margin:[7.4,19.8,7.4,19.8],image:{type:'png'},html2canvas:{scale:2,backgroundColor:'#ffffff',logging:false,windowWidth:794,scrollX:0,scrollY:0},jsPDF:{unit:'mm',format:'a4',orientation:'portrait',compress:true},pagebreak:{mode:['css','legacy'],avoid:['tr','.af-receipt-meta','.af-receipt-total','.af-receipt-legal']}}));const blob=await win.html2pdf().set(options).from(receipt).outputPdf('blob');const objectURL=URL.createObjectURL(blob);const download=document.createElement('a');download.href=objectURL;download.download=filename;document.body.append(download);download.click();download.remove();setTimeout(()=>URL.revokeObjectURL(objectURL),30000);
    }catch(error){
      // The authenticated native endpoint remains available without canvas/JavaScript.
      console.warn('Receipt browser export unavailable; using the server PDF.',error.message);location.assign(nativeURL);
    }finally{frame.remove();exporting=false;link.removeAttribute('aria-busy');}
  });
})();
