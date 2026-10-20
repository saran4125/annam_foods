/* Refresh server-rendered history without replacing the reply draft or stealing scroll. */
(() => {
  const inbox=document.querySelector('[data-inbox]');
  if(!inbox || inbox.dataset.poll!=='1')return;
  const thread=document.getElementById('wa-thread');
  const messageList=document.getElementById('wa-message-list');
  const contacts=document.getElementById('wa-contact-list');
  const note=document.getElementById('wa-poll-note');
  if(thread)thread.scrollTop=thread.scrollHeight;
  let busy=false;
  async function poll(){
    if(document.hidden || busy)return;
    busy=true;
    try{
      const url=new URL(window.location.href);url.searchParams.set('poll','1');
      const response=await fetch(url,{headers:{'Accept':'application/json'},credentials:'same-origin'});
      if(response.redirected || response.status===403){note.textContent='Your session changed. Reload to sign in again.';return;}
      if(!response.ok)throw new Error('refresh');
      const data=await response.json();
      if(contacts.innerHTML!==data.contacts)contacts.innerHTML=data.contacts;
      if(messageList && messageList.innerHTML!==data.messages){
        const atBottom=thread.scrollHeight-thread.scrollTop-thread.clientHeight<90;
        const oldTop=thread.scrollTop;
        messageList.innerHTML=data.messages;
        thread.scrollTop=atBottom?thread.scrollHeight:oldTop;
      }
      const input=document.getElementById('wa-reply'),send=document.getElementById('wa-send');
      if(input){
        input.disabled=!data.can_reply;send.disabled=!data.can_reply;
        document.getElementById('wa-window').textContent=data.window_open?'24-hour reply window is open':'Reply window closed — customer must message again';
        if(!data.window_open)document.getElementById('wa-reply-note').textContent='The 24-hour reply window closed. Ask the customer to message again.';
      }
      const unread=document.getElementById('wa-unread-total');
      if(unread)unread.textContent=`${data.unread_total} unread messages`;
      note.textContent='Up to date · refreshes automatically';
    }catch(_){note.textContent='Connection interrupted. Retrying automatically…';}
    finally{busy=false;}
  }
  window.setInterval(poll,5000);
})();
