/* Shared progressive dropdown for billing forms. Original selects own values and validation. */
(() => {
  'use strict';
  const make = (tag, className, text) => {
    const node=document.createElement(tag);
    if(className) node.className=className;
    if(text!==undefined) node.textContent=text;
    return node;
  };
  document.querySelectorAll('.billing-ui select:not([multiple]), .appearance-editor select:not([multiple])').forEach((select,index) => {
    if(select.closest('[data-line]') || select.disabled) return;
    const originalLabels=[...select.labels];
    const label=originalLabels[0]?.cloneNode(true);
    label?.querySelectorAll('select,input,textarea,[aria-hidden="true"]').forEach(node=>node.remove());
    const labelText=(label?.textContent || select.name).replace(/\*/g,'').replace(/\s+/g,' ').trim() || select.name;
    // Avoid placing interactive dropdown buttons inside the old wrapping label.
    if(select.parentElement.tagName==='LABEL'){
      const wrapper=select.parentElement;
      const field=make('div',wrapper.className);
      while(wrapper.firstChild) field.append(wrapper.firstChild);
      wrapper.replaceWith(field);
    }
    const picker=make('details','b-picker b-choice');
    const trigger=make('summary');trigger.id=`${select.id || 'billing-select-'+index}-trigger`;
    originalLabels.forEach(label=>{if(label.htmlFor===select.id) label.htmlFor=trigger.id;});
    const panel=make('div','b-picker-panel');
    const search=make('input','o-input');search.type='search';search.placeholder='Search options…';search.setAttribute('aria-label',`Search ${labelText}`);
    const options=make('div','b-picker-options');
    const count=make('p','b-picker-count');count.setAttribute('role','status');
    const error=make('p','b-choice-error');error.hidden=true;error.setAttribute('role','alert');
    function updateLabel(){
      trigger.textContent=select.selectedOptions[0]?.textContent || 'Choose an option';
      trigger.setAttribute('aria-label',`${labelText}: ${trigger.textContent}`);
      error.hidden=true;
    }
    function render(){
      options.replaceChildren();
      const query=search.value.trim().toLocaleLowerCase();
      const matching=[...select.options].filter(option=>!option.hidden && option.textContent.toLocaleLowerCase().includes(query));
      for(const option of matching){
        const button=make('button','b-picker-option b-choice-option',option.textContent);
        button.type='button';button.disabled=option.disabled || option.parentElement.disabled===true;
        button.setAttribute('aria-pressed',String(option.selected));
        button.addEventListener('click',()=>{
          select.value=option.value;
          select.dispatchEvent(new Event('input',{bubbles:true}));
          select.dispatchEvent(new Event('change',{bubbles:true}));
          picker.open=false;trigger.focus();
        });
        options.append(button);
      }
      if(!matching.length) options.append(make('p','b-muted','No matching options.'));
      count.textContent=`${matching.length} option${matching.length===1?'':'s'}`;
    }
    picker.addEventListener('toggle',()=>{
      if(!picker.open)return;
      document.querySelectorAll('.b-picker[open]').forEach(other=>{if(other!==picker)other.open=false;});
      render();search.focus();
    });
    search.addEventListener('input',render);
    search.addEventListener('keydown',event=>{
      if(event.key==='ArrowDown'||event.key==='Enter'){
        event.preventDefault();options.querySelector('button:not(:disabled)')?.focus();
      }
    });
    options.addEventListener('keydown',event=>{
      if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
      event.preventDefault();
      const buttons=[...options.querySelectorAll('button:not(:disabled)')];
      const current=buttons.indexOf(document.activeElement);
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,current+(event.key==='ArrowDown'?1:-1)));
      buttons[next]?.focus();
    });
    picker.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();picker.open=false;trigger.focus();}
    });
    select.addEventListener('change',updateLabel);
    select.addEventListener('invalid',event=>{
      event.preventDefault();error.textContent=select.validationMessage;error.hidden=false;
      picker.open=true;trigger.focus();
    });
    panel.append(search,options,count);picker.append(trigger,panel);select.after(picker,error);
    select.classList.add('b-select-native');select.setAttribute('aria-hidden','true');select.tabIndex=-1;
    select.form?.addEventListener('reset',()=>setTimeout(updateLabel,0));
    updateLabel();
  });
  document.addEventListener('click',event=>{
    document.querySelectorAll('.b-choice[open]').forEach(picker=>{if(!picker.contains(event.target))picker.open=false;});
  });
})();
