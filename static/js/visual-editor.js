/* A live server-rendered website canvas. Plain fields remain the saved source. */
(() => {
  const form=document.querySelector('#visual-design-form');if(!form)return;
  document.body.classList.add('ve-js');
  const frame=document.querySelector('#website-canvas'),layers=document.querySelector('[data-layer-list]'),layout=document.querySelector('[data-layout]');
  const status=document.querySelector('#ve-status'),error=document.querySelector('[data-canvas-error]'),loading=document.querySelector('[data-loading]');
  const element=name=>form.elements.namedItem(name);
  const library=JSON.parse(document.querySelector('#website-image-library').textContent);
  let selected='hero',imageKey='hero',device=matchMedia('(max-width:900px)').matches?'mobile':'desktop';
  const savedLabel=status.textContent;
  let renderTimer,controller,sequence=0,history=[],cursor=-1,savedSnapshot='',dragging=null;
  const rows=()=>[...layers.querySelectorAll('[data-layer]')];
  const snapshot=()=>({values:Object.fromEntries([...form.elements].filter(el=>el.name && !['csrfmiddlewaretoken','revision','action'].includes(el.name)).map(el=>[el.name,el.type==='checkbox'?el.checked:el.value])),order:rows().map(row=>row.dataset.layer)});
  const updateStatus=()=>{status.textContent=JSON.stringify(snapshot())===savedSnapshot?savedLabel:'Unsaved changes';};
  const updateHistory=()=>{document.querySelector('[data-history=undo]').disabled=cursor<=0;document.querySelector('[data-history=redo]').disabled=cursor>=history.length-1;};
  const remember=()=>{const value=JSON.stringify(snapshot());if(history[cursor]!==value){history=history.slice(0,cursor+1);history.push(value);if(history.length>60)history.shift();cursor=history.length-1;}updateHistory();updateStatus();};
  const send=data=>frame.contentWindow?.postMessage({websiteEditor:true,...data},location.origin);
  const syncOrder=()=>rows().forEach((row,index)=>{row.querySelector('input[type=number]').value=index+1;row.classList.toggle('is-hidden',!row.querySelector('input[type=checkbox]').checked);});
  const fit=()=>{
    const area=document.querySelector('[data-canvas-scroll]'),shell=document.querySelector('[data-frame-shell]');
    const width=device==='mobile'?390:1100,scale=Math.min((area.clientWidth-32)/width,1),safeScale=Math.max(scale,.1);
    const height=Math.max(500,(area.clientHeight-30)/safeScale);
    frame.style.width=width+'px';frame.style.height=height+'px';frame.style.transform=`scale(${safeScale})`;
    shell.style.width=(width*safeScale)+'px';shell.style.height=(height*safeScale)+'px';
    document.querySelector('[data-zoom]').textContent=Math.round(safeScale*100)+'%';
    document.querySelectorAll('[data-device]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.device===device)));
  };
  const mobilePanel=panel=>{layout.dataset.mobilePanel=panel;document.querySelectorAll('[data-panel]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.panel===panel)));requestAnimationFrame(fit);};
  const styleTab=style=>{document.querySelector('[data-content-panel]').hidden=style;document.querySelector('[data-style-panel]').hidden=!style;document.querySelectorAll('[data-inspector-tab]').forEach(b=>b.setAttribute('aria-pressed',String((b.dataset.inspectorTab==='design')===style)));};
  const photoPreview=src=>{const img=document.querySelector('[data-current-photo]');img.hidden=!src;document.querySelector('[data-no-photo]').hidden=!!src;if(src)img.src=src;};
  const select=(section,{field=null,image=null,src=null,scroll=false,openPanel=true}={})=>{
    selected=section;imageKey=image || (section==='brand'?'logo':['hero','offers','spotlight'].includes(section)?section:null);
    const row=rows().find(row=>row.dataset.layer===section);document.querySelector('[data-selection-title]').textContent=imageKey==='logo'?'Your store logo':row?.querySelector('[data-select-section]').textContent.trim() || (section==='brand'?'Your brand':'Your website');
    rows().forEach(row=>row.classList.toggle('is-selected',row.dataset.layer===section));
    document.querySelectorAll('[data-copy-group]').forEach(group=>group.classList.toggle('is-active',group.dataset.copyGroup===section));
    document.querySelectorAll('[data-copy-field]').forEach(label=>label.classList.toggle('is-focused',label.dataset.copyField===field));
    document.querySelector('[data-photo-panel]').hidden=!imageKey;
    document.querySelector('[data-catalog-note]').hidden=!['meals','popular','categories'].includes(section);
    if(imageKey){document.querySelector('[data-photo-label]').textContent=imageKey==='logo'?'Store logo':'Section photo';const existing=frame.contentDocument?.querySelector(`[data-canvas-image="${imageKey}"]`);photoPreview(src || element('image_'+imageKey)?.value || existing?.getAttribute('src') || '');}
    styleTab(false);send({type:'select',section,scroll});
    if(openPanel && matchMedia('(max-width:900px)').matches)mobilePanel('inspector');
  };
  const render=async()=>{
    clearTimeout(renderTimer);controller?.abort();controller=new AbortController();const current=++sequence;
    let scroll=0;try{scroll=frame.contentWindow?.scrollY || 0;}catch{}
    status.textContent='Updating your website…';error.hidden=true;
    try{
      const response=await fetch(form.dataset.renderUrl,{method:'POST',body:new FormData(form),signal:controller.signal,credentials:'same-origin'});
      if(current!==sequence)return;
      if(response.redirected)throw new Error('Your session ended. Open the kitchen dashboard to sign in again; your edits are still here.');
      if(!response.ok){const body=await response.json();const messages=Object.values(body.errors || {}).flat().map(item=>item.message || item);throw new Error(messages.join(' ') || 'Could not refresh the preview. Your edits are still here.');}
      const html=await response.text();if(current!==sequence)return;
      frame.onload=()=>{loading.hidden=true;fit();frame.contentWindow.scrollTo(0,scroll);send({type:'select',section:selected});updateStatus();};
      frame.srcdoc=html;
    }catch(reason){if(reason.name==='AbortError')return;error.textContent=reason.message;error.hidden=false;status.textContent='Check your changes';loading.hidden=true;}
  };
  const schedule=()=>{clearTimeout(renderTimer);renderTimer=setTimeout(render,450);};
  const moveBefore=(fromKey,beforeKey)=>{const from=rows().find(r=>r.dataset.layer===fromKey),before=rows().find(r=>r.dataset.layer===beforeKey);if(from && before && from!==before){layers.insertBefore(from,before);syncOrder();remember();schedule();}};
  const move=(key,direction)=>{const row=rows().find(r=>r.dataset.layer===key);if(!row)return;const next=direction==='up'?row.previousElementSibling:row.nextElementSibling;if(!next)return;if(direction==='up')layers.insertBefore(row,next);else layers.insertBefore(next,row);syncOrder();remember();schedule();};
  const renderLibrary=()=>{const grid=document.querySelector('[data-image-library]');grid.replaceChildren();library.forEach(asset=>{const button=document.createElement('button');button.type='button';button.title=asset.name;button.setAttribute('aria-label','Use '+asset.name);const img=document.createElement('img');img.src=asset.url;img.alt=asset.name;img.loading='lazy';button.append(img);button.addEventListener('click',()=>{if(!imageKey)return;element('image_'+imageKey).value=asset.url;photoPreview(asset.url);remember();schedule();});grid.append(button);});};
  form.addEventListener('input',event=>{
    const input=event.target;if(!input.name)return;
    if(input.name.startsWith('copy_')){const key=input.name.slice(5);send({type:'text',key,value:input.value});if(!frame.contentDocument?.querySelector(`[data-canvas-text="${key}"]`) || key==='spotlight.points')schedule();}
    if(['brand','paper','ink','surface_alt'].includes(input.name)){const code=input.closest('label')?.querySelector('[data-colour-code]');if(code)code.textContent=input.value;schedule();}
    remember();
  });
  form.addEventListener('change',event=>{const input=event.target;if(input.name && !input.name.startsWith('copy_')){syncOrder();remember();schedule();}});
  layers.addEventListener('click',event=>{const button=event.target.closest('[data-select-section]');if(button)select(button.dataset.selectSection,{scroll:true});});
  layers.addEventListener('keydown',event=>{if(!event.target.closest('[data-grip]') || !['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();move(event.target.closest('[data-layer]').dataset.layer,event.key==='ArrowUp'?'up':'down');});
  layers.addEventListener('pointerdown',event=>{const grip=event.target.closest('[data-grip]');if(!grip)return;event.preventDefault();dragging=grip.closest('[data-layer]');dragging.classList.add('is-dragging');grip.setPointerCapture(event.pointerId);grip.focus();});
  layers.addEventListener('pointermove',event=>{if(!dragging)return;const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-layer]');if(!target || target===dragging)return;const rect=target.getBoundingClientRect();if(event.clientY>rect.top+rect.height/2)layers.insertBefore(dragging,target.nextElementSibling);else layers.insertBefore(dragging,target);syncOrder();});
  const finishDrag=()=>{if(!dragging)return;dragging.classList.remove('is-dragging');dragging=null;syncOrder();remember();schedule();};
  layers.addEventListener('pointerup',finishDrag);layers.addEventListener('pointercancel',finishDrag);
  document.querySelectorAll('[data-device]').forEach(button=>button.addEventListener('click',()=>{device=button.dataset.device;fit();}));
  document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>{mobilePanel(button.dataset.panel);if(button.dataset.panel==='design')styleTab(true);if(button.dataset.panel==='inspector')styleTab(false);}));
  document.querySelectorAll('[data-inspector-tab]').forEach(button=>button.addEventListener('click',()=>styleTab(button.dataset.inspectorTab==='design')));
  document.querySelectorAll('[data-palette]').forEach(button=>button.addEventListener('click',()=>{element('brand').value=button.dataset.palette;element('brand').dispatchEvent(new Event('input',{bubbles:true}));}));
  document.querySelectorAll('[data-history]').forEach(button=>button.addEventListener('click',()=>{
    const next=cursor+(button.dataset.history==='undo'?-1:1);if(next<0 || next>=history.length)return;cursor=next;const state=JSON.parse(history[cursor]);
    for(const [name,value] of Object.entries(state.values)){const input=element(name);if(!input)continue;if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new Event('change'));}
    state.order.forEach(key=>{const row=rows().find(r=>r.dataset.layer===key);if(row)layers.append(row);});syncOrder();document.querySelectorAll('.ve-colour-row').forEach(row=>{row.querySelector('[data-colour-code]').textContent=row.querySelector('input').value;});updateHistory();updateStatus();render();
  }));
  document.querySelector('[data-image-upload]').addEventListener('change',async event=>{
    const file=event.target.files[0],target=imageKey;if(!file || !target)return;
    if(file.size>3*1024*1024){error.textContent='Choose a photo smaller than 3 MB.';error.hidden=false;event.target.value='';return;}
    const data=new FormData();data.append('csrfmiddlewaretoken',element('csrfmiddlewaretoken').value);data.append('image',file);
    status.textContent='Saving your photo…';error.hidden=true;
    try{const response=await fetch(form.dataset.uploadUrl,{method:'POST',body:data,credentials:'same-origin'});if(response.redirected)throw new Error('Sign in again from the kitchen dashboard to upload your photo.');const body=await response.json();if(!response.ok)throw new Error(body.error || 'Could not upload this photo.');element('image_'+target).value=body.url;library.unshift(body);renderLibrary();photoPreview(body.url);remember();render();}catch(reason){error.textContent=reason.message;error.hidden=false;status.textContent='Photo was not uploaded';}finally{event.target.value='';}
  });
  document.querySelector('[data-reset-photo]').addEventListener('click',()=>{if(!imageKey)return;element('image_'+imageKey).value='';photoPreview('');remember();render();});
  window.addEventListener('message',event=>{
    if(event.source!==frame.contentWindow || event.origin!==location.origin || !event.data?.websiteCanvas)return;
    const message=event.data;
    if(message.type==='select')select(message.section,{field:message.field,image:message.image,src:message.src});
    if(message.type==='text'){const input=element('copy_'+message.key);if(!input)return;input.value=message.value;remember();}
    if(message.type==='hide'){const checkbox=element('show_'+message.section);if(checkbox){checkbox.checked=false;syncOrder();remember();render();}}
    if(message.type==='move')move(message.section,message.direction);
    if(message.type==='reorder')moveBefore(message.section,message.before);
    if(message.type==='ready'){send({type:'select',section:selected});if(imageKey){const image=frame.contentDocument?.querySelector(`[data-canvas-image="${imageKey}"]`);photoPreview(element('image_'+imageKey)?.value || image?.getAttribute('src') || '');}}
  });
  form.addEventListener('submit',()=>{status.textContent='Saving your website…';});
  window.addEventListener('resize',fit);new ResizeObserver(fit).observe(document.querySelector('[data-canvas-scroll]'));
  syncOrder();savedSnapshot=JSON.stringify(snapshot());history=[savedSnapshot];cursor=0;updateHistory();renderLibrary();select('hero',{openPanel:false});mobilePanel('canvas');fit();render();
})();
