(()=>{
 const rows=document.querySelector('#pin-rows');
 const refresh=()=>{if(!rows)return;const unique=new Set();[...rows.rows].forEach((row,index)=>{row.cells[0].textContent=index+1;const value=row.querySelector('input').value.trim();if(value)unique.add(value);});document.querySelector('#pin-count').textContent=unique.size+' unique pincodes';};
 const add=value=>{const row=document.createElement('tr');row.innerHTML='<td></td><td><input name="pincodes[]" inputmode="numeric" maxlength="6" pattern="[1-9][0-9]{5}" aria-label="Delivery pincode"></td><td><button type="button" class="o-btn" data-remove-pin>Remove</button></td>';row.querySelector('input').value=value||'';rows.append(row);refresh();return row;};
 document.querySelector('#add-pin')?.addEventListener('click',()=>add('').querySelector('input').focus());
 rows?.addEventListener('click',event=>{if(event.target.closest('[data-remove-pin]')){event.target.closest('tr').remove();if(!rows.rows.length)add('');refresh();}});
 rows?.addEventListener('input',refresh);rows?.addEventListener('paste',event=>{const input=event.target;if(input.tagName!=='INPUT')return;const values=event.clipboardData.getData('text').trim().split(/\r?\n/).map(s=>s.trim());if(values.length<2)return;if(values.some(s=>!/^\d{6}$/.test(s))){event.preventDefault();alert('Paste one column containing six-digit pincodes.');return;}event.preventDefault();input.value=values.shift();values.forEach(add);refresh();});refresh();
 document.querySelector('#booking-filter')?.addEventListener('input',event=>{const q=event.target.value.toLocaleLowerCase();document.querySelectorAll('.php-booking-item').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase().includes(q));});
})();
