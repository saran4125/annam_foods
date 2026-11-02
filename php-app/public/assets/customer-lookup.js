/* Phone-first lookup; saved values stay editable and late replies cannot replace typing. */
(() => {
 'use strict';
 const phone=document.getElementById('customer-phone');if(!phone)return;
 const status=document.getElementById('customer-lookup-status');
 const fields=['name','address','city','state','country','postal_code','zone','fulfilment_method'];
 const input=name=>document.getElementById('customer-'+name);
 const key=()=>{const value=phone.value.replace(/[\s()+-]/g,'');return value.length===12&&value.startsWith('91')?value.slice(2):value;};
 let timer,controller,revision=0,lastKey='',filled={};
 function clearPrevious(){for(const[name,value]of Object.entries(filled)){const field=input(name);if(field.value===value)field.value=name==='state'?'Tamil Nadu':name==='country'?'India':name==='fulfilment_method'?'local':'';}filled={};}
 async function lookup(version){const currentKey=key();if(version!==revision||!/^[0-9]{10,15}$/.test(currentKey)||currentKey===lastKey)return;lastKey=currentKey;controller=new AbortController();const before=Object.fromEntries(fields.map(name=>[name,input(name).value]));status.textContent='Looking for saved customer details…';
 try{const response=await fetch('/manage/customer-lookup/?phone='+encodeURIComponent(phone.value),{signal:controller.signal,cache:'no-store',headers:{Accept:'application/json'}});if(!response.ok)throw Error();const result=await response.json();if(version!==revision||key()!==currentKey)return;if(!result.found){status.textContent='New customer. Enter name and delivery details.';return;}
 for(const name of fields){const field=input(name);if(field.value!==before[name])continue;field.value=result.details[name]??'';if(name==='fulfilment_method'&&!field.value)field.value='local';filled[name]=field.value;field.dispatchEvent(new Event('change',{bubbles:true}));}status.textContent=result.needs_area_selection?'Saved details filled. Select the current delivery area. You can edit all details.':'Saved details filled. Review the address; you can edit all details.';
 }catch(error){if(error.name==='AbortError'||version!==revision)return;lastKey='';status.textContent='Saved details unavailable. Enter them manually, or leave the phone field to retry.';}}
 phone.addEventListener('input',()=>{clearTimeout(timer);if(key()===lastKey)return;controller?.abort();revision++;lastKey='';clearPrevious();status.textContent='Enter a phone number to find saved details.';const version=revision;timer=setTimeout(()=>lookup(version),450);});phone.addEventListener('blur',()=>{clearTimeout(timer);lookup(revision);});if(phone.value)lookup(revision);
})();
