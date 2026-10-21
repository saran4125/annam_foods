/* Runs only in the authenticated editor's trusted, sandboxed website frame. */
(() => {
  const send = data => { if (window.parent !== window) window.parent.postMessage({websiteCanvas:true,...data}, window.parent.location.origin); };
  const names = {hero:'Welcome hero',offers:'Offers & banners',meals:'Daily menu',numbers:'Kitchen highlights',categories:'Shop categories',showcase:'Food favourites',popular:'Popular products',spotlight:'Product spotlight',story:'How ordering works',closing:'Contact & visit'};
  document.documentElement.classList.add('website-canvas');
  document.querySelectorAll('[data-reveal]').forEach(el=>el.classList.add('is-in'));
  document.querySelectorAll('[aria-hidden=true]').forEach(el=>{if(el.closest('.hero2-art'))el.removeAttribute('aria-hidden');});
  const select = section => {
    document.querySelectorAll('[data-home-section],[data-canvas-section]').forEach(el=>el.classList.toggle('canvas-selected',(el.dataset.homeSection || el.dataset.canvasSection)===section));
  };
  document.querySelectorAll('[data-home-section]').forEach(section=>{
    const key=section.dataset.homeSection;
    if(section.getBoundingClientRect().height<30){
      const empty=document.createElement('div');empty.className='canvas-section-empty';
      empty.textContent=`${names[key] || key} · Select to add content or show your available items`;
      section.append(empty);
    }
    const toolbar=document.createElement('div');toolbar.className='canvas-section-toolbar';
    const handle=document.createElement('button');handle.type='button';handle.draggable=true;handle.textContent=`⠿ ${names[key] || key}`;
    handle.setAttribute('aria-label',`Drag ${names[key] || key} to rearrange`);
    handle.addEventListener('dragstart',event=>{event.dataTransfer.setData('text/plain',key);event.dataTransfer.effectAllowed='move';});
    handle.addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();send({type:'move',section:key,direction:event.key==='ArrowUp'?'up':'down'});}});
    const hide=document.createElement('button');hide.type='button';hide.textContent='Hide';hide.setAttribute('aria-label',`Hide ${names[key] || key}`);
    hide.addEventListener('click',event=>{event.stopImmediatePropagation();send({type:'hide',section:key});});
    toolbar.append(handle,hide);section.prepend(toolbar);
    section.addEventListener('dragover',event=>{event.preventDefault();section.classList.add('canvas-drop-target');});
    section.addEventListener('dragleave',()=>section.classList.remove('canvas-drop-target'));
    section.addEventListener('drop',event=>{event.preventDefault();section.classList.remove('canvas-drop-target');const from=event.dataTransfer.getData('text/plain');if(from && from!==key)send({type:'reorder',section:from,before:key});});
  });
  document.querySelectorAll('[data-canvas-text]').forEach(el=>{
    const key=el.dataset.canvasText;el.contentEditable='plaintext-only';el.spellcheck=true;el.tabIndex=0;
    el.setAttribute('role','textbox');el.setAttribute('aria-label',`Edit ${key.split('.').at(-1).replaceAll('_',' ')}`);
    let original=el.textContent;
    el.addEventListener('focus',()=>{original=el.textContent;select(el.closest('[data-home-section]')?.dataset.homeSection);send({type:'select',section:key.split('.')[0],field:key});});
    el.addEventListener('input',()=>send({type:'text',key,value:el.innerText}));
    if(key.startsWith('footer.'))el.addEventListener('blur',()=>send({type:'refresh'}));
    el.addEventListener('keydown',event=>{
      if(event.key==='Escape'){el.textContent=original;send({type:'text',key,value:original});el.blur();}
      if(event.key==='Enter' && !['body','points','address'].includes(key.split('.').at(-1))){event.preventDefault();el.blur();}
    });
    el.addEventListener('paste',event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));});
  });
  document.querySelectorAll('[data-canvas-image]').forEach(el=>{
    el.tabIndex=0;el.setAttribute('role','button');el.setAttribute('aria-label',`Replace ${el.dataset.photoPosition || el.dataset.canvasImage} photo`);
    el.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();el.click();}});
  });
  document.addEventListener('submit',event=>event.preventDefault(),true);
  document.addEventListener('click',event=>{
    const target=event.target;
    if(target.closest('.canvas-section-toolbar'))return;
    const image=target.closest('[data-canvas-image]');
    const text=target.closest('[data-canvas-text]');
    const list=target.closest('[data-canvas-list]');
    const container=target.closest('[data-home-section],[data-canvas-section]');
    const section=container?.dataset.homeSection || container?.dataset.canvasSection;
    if(target.closest('a,button,input,select,form')){event.preventDefault();event.stopImmediatePropagation();}
    if(image){send({type:'select',section:image.dataset.canvasImage==='logo'?'brand':section || 'hero',image:image.dataset.canvasImage,src:image.getAttribute('src') || ''});}
    else if(text){send({type:'select',section:text.dataset.canvasText.split('.')[0],field:text.dataset.canvasText});text.focus();}
    else if(list){send({type:'select',section,field:list.dataset.canvasList});}
    else if(section){send({type:'select',section});}
    if(section)select(section);
  },true);
  window.addEventListener('message',event=>{
    if(event.source!==window.parent || event.origin!==window.parent.location.origin || !event.data?.websiteEditor)return;
    const message=event.data;
    if(message.type==='select'){
      select(message.section);
      const section=[...document.querySelectorAll('[data-home-section],[data-canvas-section]')].find(el=>(el.dataset.homeSection || el.dataset.canvasSection)===message.section);
      if(message.scroll)section?.scrollIntoView({block:'start',behavior:'smooth'});
    }
    if(message.type==='text'){
      document.querySelectorAll('[data-canvas-text]').forEach(el=>{if(el.dataset.canvasText===message.key && document.activeElement!==el){el.textContent=message.value;const h=el.closest('h1');if(h)h.setAttribute('aria-label',message.value);}});
    }
  });
  send({type:'ready'});
})();
