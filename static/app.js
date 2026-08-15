let token=localStorage.getItem("qtalk_token")||"",me=null,ws=null,chats=[],activeChat=null,replyId=null,typingTimer=null,pc=null,localStream=null,incomingCallData=null,selectedGroupMembers=new Set(),wsStop=false,wsReconnectTimer=null,pingTimer=null,pendingMessages=new Map(),chatLoadSeq=0;

const $=id=>document.getElementById(id);
function esc(s=""){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c]))}
function avatarHTML(u,cls="avatar"){let initial=esc((u?.name||"U").trim().slice(0,1).toUpperCase());return `<div class="${cls}"${u?.avatar_url?` style="background-image:url('${esc(u.avatar_url)}')"`:``}>${u?.avatar_url?"":initial}</div>`}
async function api(url,opt={}){opt.credentials="same-origin";opt.headers={...(opt.headers||{})};if(token)opt.headers.Authorization=`Bearer ${token}`;if(opt.body&&!(opt.body instanceof FormData))opt.headers["Content-Type"]="application/json";let r=await fetch(url,opt);let d={};try{d=await r.json()}catch{}if(r.status===401){logout(true);throw Error("Unauthorized")}if(!r.ok)throw Error(d.detail||"Request failed");return d}
function toast(msg){let t=$("toast");t.textContent=msg;t.classList.remove("hidden");clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.add("hidden"),2600)}

async function boot(){
  wsStop=false;
  // The server-side session cookie can restore a session if localStorage was
  // cleared. The API call below is the source of truth.
  if(!token){
    try{
      me=await api("/api/me");
      $("login").classList.add("hidden");
      renderMe();
      await loadChats();
      connectWS();
      return;
    }catch(e){}
    $("login").classList.remove("hidden");
    return;
  }
  try{
    me=await api("/api/me");
    renderMe();
    $("login").classList.add("hidden");
    await loadChats();
    connectWS();
  }catch(e){
    console.error(e);
    // Do NOT wipe a valid token just because the backend is temporarily
    // unreachable. Only a real 401 in api() clears the session.
    if(!token) $("login").classList.remove("hidden");
    else toast("Qtalk is reconnecting…");
  }
}
function renderMe(){ $("myName").textContent=me.name;$("myPhone").textContent=me.phone;$("myAbout").textContent=me.about||"";setAvatar($("myAvatar"),me)}
function setAvatar(el,u){if(!el)return;el.textContent=u?.avatar_url?"":((u?.name||"Q").slice(0,1).toUpperCase());el.style.backgroundImage=u?.avatar_url?`url("${u.avatar_url}")`:""}
async function requestOtp(){try{let phone=$("phone").value.trim();if(!phone)return toast("Enter phone number");let r=await fetch("/api/auth/send-otp",{credentials:"same-origin",method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Could not send OTP");$("otpArea").classList.remove("hidden");$("otpHint").textContent=d.dev_otp?`Development OTP: ${d.dev_otp}`:"OTP sent";$("otp").focus()}catch(e){toast(e.message)}}
async function verifyOtp(){try{let r=await fetch("/api/auth/verify-otp",{credentials:"same-origin",method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:$("phone").value.trim(),otp:$("otp").value.trim(),name:$("name").value.trim()})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Invalid OTP");token=d.token;localStorage.setItem("qtalk_token",token);$("login").classList.add("hidden");await boot()}catch(e){toast(e.message)}}
function logout(silent=false){
  wsStop=true;clearTimeout(wsReconnectTimer);clearInterval(pingTimer);
  if(ws){try{ws.close()}catch{}}
  ws=null;token="";me=null;localStorage.removeItem("qtalk_token");
  fetch("/api/auth/logout",{method:"POST",credentials:"same-origin"}).catch(()=>{})
  if(!silent)location.reload();else $("login").classList.remove("hidden")
}

async function loadChats(){
  const seq=++chatLoadSeq;
  const data=await api("/api/chats");
  if(seq!==chatLoadSeq)return;
  chats=data;
  if(!$("search").value.trim())renderList("chats",chats);
}
function renderList(mode="chats",items=null){
  let list=$("list");list.innerHTML="";
  if(mode==="status"){loadStatus();return}
  let data=items||chats;
  if(!data.length){list.innerHTML='<div class="empty-search">No chats yet.<br>Use <b>＋</b> to find a Qtalk user.</div>';return}
  data.forEach(c=>{
    let title=c.title||"Chat",user=c.other||{name:title},div=document.createElement("div");
    div.className="list-item";div.onclick=()=>openChat(c);
    div.innerHTML=`${avatarHTML(user)}<div class="list-main"><b>${esc(title)}</b><small>${esc(c.last||"Start a conversation")}</small></div>${c.unread?`<span class="badge">${c.unread}</span>`:""}`;
    list.appendChild(div)
  })
}
async function showTab(tab,btn){
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));btn.classList.add("active");clearSearch();
  if(tab==="chats")await loadChats();
  else if(tab==="contacts"){let cs=await api("/api/contacts");$("list").innerHTML=cs.length?cs.map(c=>`<div class="list-item" onclick="startDirect(${c.id})">${avatarHTML(c)}<div class="list-main"><b>${esc(c.name)}</b><small>${esc(c.phone)}</small></div></div>`).join(""):'<div class="empty-search">No saved contacts.</div>'}
  else loadStatus()
}
async function startDirect(id){try{let d=await api(`/api/chats/direct/${id}`,{method:"POST"});await loadChats();let c=chats.find(x=>x.id===d.id);if(c)await openChat(c);closeModal("newChatModal")}catch(e){toast(e.message)}}
async function openChat(c){
  activeChat=c;$("empty").classList.add("hidden");$("conversation").classList.remove("hidden");$("conversation").classList.add("open");
  $("chatTitle").textContent=c.title;setAvatar($("chatAvatar"),c.other||{name:c.title});
  $("chatStatus").textContent=c.kind==="group"?`${c.member_ids.length} members`:c.other?.is_online?"online":"offline";
  await loadMessages();await api(`/api/chats/${c.id}/read`,{method:"POST"}).catch(()=>{});await loadChats();
  if(innerWidth<760)$("conversation").closest(".chat").classList.add("open")
}
function closeChat(){$("conversation").closest(".chat").classList.remove("open");$("conversation").classList.remove("open");$("empty").classList.remove("hidden");activeChat=null;replyId=null;closePopup("chatMenu");toggleAttach(false);toggleEmoji(false);$("replyBar").classList.add("hidden")}
async function loadMessages(){if(!activeChat)return;try{let ms=await api(`/api/chats/${activeChat.id}/messages?limit=300`);renderMessages(ms)}catch(e){toast(e.message)}}

function formatLocalDateTime(timestamp){
  if(!timestamp) return "";
  const d=new Date(timestamp);
  if(Number.isNaN(d.getTime())) return "";
  const now=new Date();
  const time=d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",hour12:true});
  const sameDay=d.getFullYear()===now.getFullYear()&&d.getMonth()===now.getMonth()&&d.getDate()===now.getDate();
  if(sameDay) return time;
  const yesterday=new Date(now);yesterday.setDate(now.getDate()-1);
  const wasYesterday=d.getFullYear()===yesterday.getFullYear()&&d.getMonth()===yesterday.getMonth()&&d.getDate()===yesterday.getDate();
  if(wasYesterday) return `Yesterday, ${time}`;
  return `${d.toLocaleDateString([], {day:"2-digit",month:"2-digit",year:"numeric"})}, ${time}`;
}

function renderMessages(ms){
  let box=$("messages");box.innerHTML="";ms.forEach(renderMessage);box.scrollTop=box.scrollHeight;
  let pinned=ms.find(m=>m.pinned);if(pinned){$("pinnedBar").textContent=`📌 ${pinned.text||pinned.file_name||"Pinned message"}`;$("pinnedBar").dataset.id=pinned.id;$("pinnedBar").classList.remove("hidden")}else $("pinnedBar").classList.add("hidden")
}
function renderMessage(m){
  let box=$("messages");if($(`m-${m.id}`))return;
  let div=document.createElement("div");div.className=`bubble ${m.mine?"mine":"theirs"}`;div.id=`m-${m.id}`;
  let body=m.deleted?"<i>This message was deleted</i>":esc(m.text||"");
  if(m.media_url){if(m.media_type==="image")body+=`<img class="media" src="${esc(m.media_url)}" onclick="window.open('${esc(m.media_url)}','_blank')">`;else if(m.media_type==="audio")body+=`<audio controls src="${esc(m.media_url)}"></audio>`;else if(m.media_type==="video")body+=`<video class="media" controls src="${esc(m.media_url)}"></video>`;else body+=`<a href="${esc(m.media_url)}" target="_blank" rel="noopener">📎 ${esc(m.file_name||"Document")}</a>`}
  let reactions=m.reactions?.length?`<div class="reaction-row">${m.reactions.map(r=>esc(r.emoji)).join(" ")}</div>`:"";
  let ticks=m.mine?`<span class="ticks">${m.read?"✓✓":"✓"}</span>`:"";
  let actionButtons=`<button title="Reply" onclick="replyTo(${m.id})">↩</button><button title="Heart" onclick="react(${m.id},'❤️')">❤️</button><button title="Star" onclick="starMsg(${m.id})">${m.starred?"★":"☆"}</button><button title="Pin" onclick="pinMsg(${m.id})">${m.pinned?"📌":"📍"}</button>`;
  if(m.mine&&!m.deleted)actionButtons+=`<button title="Edit" onclick="editMsg(${m.id})">✎</button><button title="Delete" onclick="delMsg(${m.id})">🗑</button>`;
  div.innerHTML=`<div class="msg-actions">${actionButtons}</div>${m.reply_to_id?`<div class="reply-mini">↩ Reply to #${m.reply_to_id}</div>`:""}<span>${body}</span><span class="time">${formatLocalDateTime(m.created_at)} ${m.edited?" · edited ":""}${ticks}</span>${reactions}`;
  box.appendChild(div)
}
async function sendText(){
  let input=$("messageInput"),text=input.value.trim();if(!activeChat||!text)return;
  let clientId=crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`,payload={type:"message",chat_id:activeChat.id,text,reply_to_id:replyId,client_id:clientId};
  pendingMessages.set(clientId,{text});
  input.value="";replyId=null;$("replyBar").classList.add("hidden");
  if(ws&&ws.readyState===WebSocket.OPEN){ws.send(JSON.stringify(payload));}
  else{
    try{await api("/api/messages",{method:"POST",body:JSON.stringify({chat_id:activeChat.id,text:payload.text,reply_to_id:payload.reply_to_id,client_id:clientId})})}
    catch(e){pendingMessages.delete(clientId);input.value=text;toast("Connection lost. Message not sent.")}
  }
}
function keySend(e){if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendText()}}
function pickFile(){toggleAttach(false);$("fileInput").click()}
async function sendFile(){
  let f=$("fileInput").files[0];if(!f||!activeChat)return;
  try{let fd=new FormData();fd.append("file",f);await api(`/api/chats/${activeChat.id}/media`,{method:"POST",body:fd});$("fileInput").value="";await loadChats()}
  catch(e){toast(e.message)}
}
function toggleAttach(force){let el=$("attachMenu");if(force===false)el.classList.add("hidden");else el.classList.toggle("hidden");closePopup("chatMenu")}
function toggleEmoji(force){let el=$("emojiMenu");if(force===false)el.classList.add("hidden");else el.classList.toggle("hidden")}
function addEmoji(x){$("messageInput").value+=x;$("messageInput").focus();toggleEmoji(false)}
async function delMsg(id){if(!confirm("Delete this message for everyone?"))return;try{await api(`/api/messages/${id}`,{method:"DELETE"})}catch(e){toast(e.message)}}
async function editMsg(id){let node=$(`m-${id}`);let old=node?.innerText?.replace(/\d{1,2}:\d{2}.*/,"").trim()||"";let text=prompt("Edit message",old);if(text===null||!text.trim())return;try{await api(`/api/messages/${id}`,{method:"PATCH",body:JSON.stringify({text:text.trim()})})}catch(e){toast(e.message)}}
function replyTo(id){replyId=id;$("replyBar").innerHTML=`↩ Replying to message #${id} <button onclick="replyId=null;$('replyBar').classList.add('hidden')">×</button>`;$("replyBar").classList.remove("hidden");$("messageInput").focus()}
async function react(id,emoji){try{await api(`/api/messages/${id}/reaction`,{method:"POST",body:JSON.stringify({emoji})})}catch(e){toast(e.message)}}
async function starMsg(id){try{await api(`/api/messages/${id}/star`,{method:"POST"})}catch(e){toast(e.message)}}
async function pinMsg(id){try{await api(`/api/messages/${id}/pin`,{method:"POST"})}catch(e){toast(e.message)}}
function jumpToPinned(){let id=$("pinnedBar").dataset.id;if(id)$(`m-${id}`)?.scrollIntoView({behavior:"smooth",block:"center"})}
function typingNow(){
  if(!ws||ws.readyState!==WebSocket.OPEN||!activeChat)return;
  let to=activeChat.kind==="direct"?activeChat.other?.id:null;if(!to)return;
  ws.send(JSON.stringify({type:"typing",to_user_id:to,chat_id:activeChat.id,is_typing:true}));
  clearTimeout(typingTimer);typingTimer=setTimeout(()=>{if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:"typing",to_user_id:to,chat_id:activeChat.id,is_typing:false}))},1000)
}
function connectWS(){
  if(wsStop)return;
  clearTimeout(wsReconnectTimer);clearInterval(pingTimer);
  try{ws?.close()}catch{}
  let proto=location.protocol==="https:"?"wss://":"ws://";
  ws=new WebSocket(proto+location.host+"/ws");
  ws.onopen=()=>{ws.send(JSON.stringify({token:token||null}));pingTimer=setInterval(()=>{if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:"ping"}))},25000)}
  ws.onmessage=async e=>{
    let d;try{d=JSON.parse(e.data)}catch{return}
    if(d.type==="ready")return;
    if(d.type==="pong")return;
    if(d.type==="message"){
      if(activeChat&&d.message.chat_id===activeChat.id){renderMessage(d.message);$("messages").scrollTop=$("messages").scrollHeight;api(`/api/chats/${activeChat.id}/read`,{method:"POST"}).catch(()=>{})}
      await loadChats()
    }else if(d.type==="message_ack"){pendingMessages.delete(d.client_id);if(activeChat&&d.message.chat_id===activeChat.id){renderMessage(d.message);$("messages").scrollTop=$("messages").scrollHeight}}
    else if(d.type==="message_error"){pendingMessages.delete(d.client_id);toast(d.message||"Message failed")}
    else if(d.type==="message_updated"){if(activeChat&&d.message.chat_id===activeChat.id)await loadMessages();await loadChats()}
    else if(d.type==="message_deleted"){$(`m-${d.message_id}`)?.remove();await loadChats()}
    else if(d.type==="reaction"||d.type==="message_meta"){if(activeChat)await loadMessages()}
    else if(d.type==="read"||d.type==="delivery"){if(activeChat)await loadMessages();await loadChats()}
    else if(d.type==="typing"&&activeChat&&d.chat_id===activeChat.id){$("typing").classList.toggle("hidden",!d.is_typing)}
    else if(d.type==="presence"){let c=chats.find(x=>x.other?.id===d.user_id);if(c){c.other.is_online=d.online;if(activeChat?.other?.id===d.user_id)$("chatStatus").textContent=d.online?"online":"offline";if(!$("search").value.trim())renderList("chats",chats)}}
    else if(d.type==="call")handleCallSignal(d)
  };
  ws.onclose=()=>{clearInterval(pingTimer);if(!wsStop){clearTimeout(wsReconnectTimer);wsReconnectTimer=setTimeout(connectWS,2000)}}
  ws.onerror=()=>{}
}
let searchTimer=null;
async function searchEverything(){
  clearTimeout(searchTimer);let q=$("search").value.trim();$("clearSearch").classList.toggle("hidden",!q);
  if(!q){renderList("chats",chats);return}
  searchTimer=setTimeout(async()=>{
    try{
      let people=await api(`/api/users/search?q=${encodeURIComponent(q)}`),chatMatches=chats.filter(c=>(c.title||"").toLowerCase().includes(q.toLowerCase())||(c.last||"").toLowerCase().includes(q.toLowerCase()));
      let list=$("list");list.innerHTML="";
      if(people.length){let h=document.createElement("div");h.className="search-section";h.textContent="People on Qtalk";list.appendChild(h)}
      people.forEach(u=>{let div=document.createElement("div");div.className="list-item";div.onclick=()=>startDirect(u.id);div.innerHTML=`${avatarHTML(u)}<div class="list-main"><b>${esc(u.name)}</b><small>${esc(u.phone)} · ${u.is_online?"online":"offline"}</small></div>`;list.appendChild(div)});
      if(chatMatches.length){let h=document.createElement("div");h.className="search-section";h.textContent="Chats";list.appendChild(h)}
      chatMatches.forEach(c=>{let div=document.createElement("div");div.className="list-item";div.onclick=()=>openChat(c);div.innerHTML=`${avatarHTML(c.other||{name:c.title})}<div class="list-main"><b>${esc(c.title)}</b><small>${esc(c.last||"Start a conversation")}</small></div>`;list.appendChild(div)});
      if(!people.length&&!chatMatches.length)list.innerHTML='<div class="empty-search">No Qtalk user or chat found.<br><br>Phone search accepts 10 digits, +91, spaces and hyphens.</div>'
    }catch(e){if(e.message.includes("Too many"))toast(e.message)}
  },220)
}
function clearSearch(){$("search").value="";$("clearSearch").classList.add("hidden");renderList("chats",chats)}
function openNewChat(){$("newChatModal").classList.remove("hidden");$("newChatSearch").value="";$("newChatResults").innerHTML='<div class="empty-search">Type a name or phone number.</div>';$("newChatSearch").focus()}
async function searchNewChat(){let q=$("newChatSearch").value.trim();if(q.length<2){$("newChatResults").innerHTML='<div class="empty-search">Type at least 2 characters or digits.</div>';return}try{let people=await api(`/api/users/search?q=${encodeURIComponent(q)}`);$("newChatResults").innerHTML=people.length?people.map(u=>`<div class="result-row" onclick="startDirect(${u.id})">${avatarHTML(u)}<div class="list-main"><b>${esc(u.name)}</b><small>${esc(u.phone)} · ${u.is_online?"online":"offline"}</small></div></div>`).join(""):'<div class="empty-search">No Qtalk account found.</div>'}catch(e){toast(e.message)}}
function openGroupModal(){closeModal("newChatModal");$("groupModal").classList.remove("hidden");selectedGroupMembers.clear();$("groupMembers").innerHTML='<div class="empty-search">Search members above.</div>'}
async function searchGroupMembers(){let q=$("groupSearch").value.trim();if(q.length<2){$("groupMembers").innerHTML='<div class="empty-search">Type a name or phone.</div>';return}try{let people=await api(`/api/users/search?q=${encodeURIComponent(q)}`);$("groupMembers").innerHTML=people.map(u=>`<label class="result-row"><input class="check" type="checkbox" ${selectedGroupMembers.has(u.id)?"checked":""} onchange="toggleGroupMember(${u.id},this.checked)">${avatarHTML(u)}<div class="list-main"><b>${esc(u.name)}</b><small>${esc(u.phone)}</small></div></label>`).join("")||'<div class="empty-search">No user found.</div>'}catch(e){toast(e.message)}}
function toggleGroupMember(id,checked){if(checked)selectedGroupMembers.add(id);else selectedGroupMembers.delete(id)}
async function createGroup(){let title=$("groupTitle").value.trim();if(!title)return toast("Enter group subject");if(!selectedGroupMembers.size)return toast("Select at least one member");try{let d=await api("/api/chats/group",{method:"POST",body:JSON.stringify({title,member_ids:[...selectedGroupMembers]})});closeModal("groupModal");await loadChats();let c=chats.find(x=>x.id===d.id);if(c)await openChat(c)}catch(e){toast(e.message)}}
function openContactModal(){closeModal("newChatModal");$("contactModal").classList.remove("hidden")}
async function saveContact(){try{await api("/api/contacts",{method:"POST",body:JSON.stringify({phone:$("contactPhone").value,nickname:$("contactName").value})});closeModal("contactModal");toast("Contact saved");await showTab("contacts",document.querySelectorAll(".tab")[1])}catch(e){toast(e.message)}}
function toggleDark(){document.body.classList.toggle("dark");localStorage.setItem("dark",document.body.classList.contains("dark"))}
function editProfile(){$("profileName").value=me.name;$("profileAbout").value=me.about||"";setAvatar($("profileAvatar"),me);$("profileModal").classList.remove("hidden")}
async function saveProfile(){try{me=await api("/api/me",{method:"PUT",body:JSON.stringify({name:$("profileName").value,about:$("profileAbout").value})});renderMe();closeModal("profileModal");toast("Profile updated")}catch(e){toast(e.message)}}
async function uploadAvatar(){let f=$("avatarInput").files[0];if(!f)return;try{let fd=new FormData();fd.append("file",f);let d=await api("/api/me/avatar",{method:"POST",body:fd});me.avatar_url=d.avatar_url;renderMe();setAvatar($("profileAvatar"),me);toast("Profile photo updated")}catch(e){toast(e.message)}}
function openStatus(){$("statusModal").classList.remove("hidden")}
function closeModal(id){$(id).classList.add("hidden")}
function closePopup(id){$(id)?.classList.add("hidden")}
async function postStatus(){try{await api("/api/status",{method:"POST",body:JSON.stringify({text:$("statusText").value,background:$("statusBg").value})});$("statusText").value="";closeModal("statusModal");await loadStatus();toast("Status posted")}catch(e){toast(e.message)}}
async function loadStatus(){let s=await api("/api/status");$("list").innerHTML=s.length?s.map(x=>`<div class="list-item ${x.viewed?"status-viewed":""}" onclick="viewStatus(${x.id})">${avatarHTML({name:x.user_name,avatar_url:x.avatar_url})}<div class="list-main"><b>${esc(x.user_name)}</b><small>${esc(x.text||"Photo status")} · ${formatLocalDateTime(x.created_at)}</small></div></div>`).join(""):'<div class="empty-search">No active statuses.</div>'}
async function viewStatus(id){await api(`/api/status/${id}/view`,{method:"POST"}).catch(()=>{});toast("Status viewed")}
function showChatInfo(){
  if(!activeChat)return;
  let text=activeChat.kind==="group"?`Group: ${activeChat.title}\nMembers: ${activeChat.member_ids.length}`:`Name: ${activeChat.title}\nPhone: ${activeChat.other?.phone||""}\nAbout: ${activeChat.other?.about||""}`;
  alert(text);closePopup("chatMenu")
}
function openChatMenu(){$("chatMenu").classList.toggle("hidden");toggleAttach(false);toggleEmoji(false)}
async function toggleMute(){if(!activeChat)return;try{let muted=!activeChat.muted;let d=await api(`/api/chats/${activeChat.id}/settings`,{method:"POST",body:JSON.stringify({muted})});activeChat.muted=d.muted;closePopup("chatMenu");toast(muted?"Chat muted":"Chat unmuted")}catch(e){toast(e.message)}}
async function toggleArchive(){if(!activeChat)return;try{await api(`/api/chats/${activeChat.id}/settings`,{method:"POST",body:JSON.stringify({archived:true})});closePopup("chatMenu");activeChat=null;$("conversation").classList.add("hidden");$("empty").classList.remove("hidden");await loadChats();toast("Chat archived")}catch(e){toast(e.message)}}
async function clearChatMessages(){if(!activeChat)return;if(!confirm("Clear this chat for you?"))return;try{await api(`/api/chats/${activeChat.id}/clear`,{method:"POST"});await loadMessages();await loadChats();closePopup("chatMenu");toast("Chat cleared for you")}catch(e){toast(e.message)}}
async function deleteChatLocal(){await toggleArchive()}
async function blockCurrentUser(){if(!activeChat?.other?.id)return toast("Group chats cannot be blocked");if(!confirm(`Block ${activeChat.title}?`))return;try{await api(`/api/blocks/${activeChat.other.id}`,{method:"POST"});closeChat();await loadChats();toast("User blocked")}catch(e){toast(e.message)}}
async function searchInChat(){
  if(!activeChat)return;let q=prompt("Search in this chat");if(!q?.trim())return;
  try{let ms=await api(`/api/chats/${activeChat.id}/search?q=${encodeURIComponent(q.trim())}`);if(!ms.length)return toast("No message found");renderMessages(ms);$(`m-${ms[0].id}`)?.scrollIntoView({behavior:"smooth",block:"center"})}catch(e){toast(e.message)}
}
async function startCall(kind){
  if(!activeChat||activeChat.kind==="group")return toast("Calls are currently for direct chats.");
  if(!ws||ws.readyState!==WebSocket.OPEN)return toast("Realtime connection is offline.");
  try{
    let to=activeChat.other.id;localStream=await navigator.mediaDevices.getUserMedia(kind==="video"?{audio:true,video:true}:{audio:true,video:false});
    $("localVideo").srcObject=localStream;$("callTitle").textContent=`Calling ${activeChat.title}…`;$("callModal").classList.remove("hidden");
    pc=new RTCPeerConnection({iceServers:[{urls:"stun:stun.l.google.com:19302"}]});
    localStream.getTracks().forEach(t=>pc.addTrack(t,localStream));pc.onicecandidate=e=>e.candidate&&ws.send(JSON.stringify({type:"call",action:"candidate",to_user_id:to,candidate:e.candidate}));pc.ontrack=e=>$("remoteVideo").srcObject=e.streams[0];
    let offer=await pc.createOffer();await pc.setLocalDescription(offer);ws.send(JSON.stringify({type:"call",action:"offer",to_user_id:to,offer}))
  }catch(e){toast("Camera/microphone permission was not granted.")}
}
function handleIncomingCall(d){if(d.action!=="offer")return;incomingCallData=d;$("incomingTitle").textContent=`Incoming call`;$("incomingType").textContent=d.offer?.sdp?.includes("m=video")?"Video call":"Voice call";$("incomingCall").classList.remove("hidden")}
async function acceptIncomingCall(){
  let d=incomingCallData;if(!d)return;closeModal("incomingCall");
  try{
    let video=!!d.offer?.sdp?.includes("m=video");localStream=await navigator.mediaDevices.getUserMedia({audio:true,video});$("localVideo").srcObject=localStream;$("callTitle").textContent="Connected call";$("callModal").classList.remove("hidden");
    pc=new RTCPeerConnection({iceServers:[{urls:"stun:stun.l.google.com:19302"}]});localStream.getTracks().forEach(t=>pc.addTrack(t,localStream));pc.onicecandidate=e=>e.candidate&&ws?.send(JSON.stringify({type:"call",action:"candidate",to_user_id:d.from_user_id,candidate:e.candidate}));pc.ontrack=e=>$("remoteVideo").srcObject=e.streams[0];
    await pc.setRemoteDescription(d.offer);let ans=await pc.createAnswer();await pc.setLocalDescription(ans);ws?.send(JSON.stringify({type:"call",action:"answer",to_user_id:d.from_user_id,answer:ans}));incomingCallData=null
  }catch(e){toast("Could not access camera/microphone");incomingCallData=null}
}
function rejectIncomingCall(){if(incomingCallData)ws?.send(JSON.stringify({type:"call",action:"hangup",to_user_id:incomingCallData.from_user_id}));incomingCallData=null;closeModal("incomingCall")}
async function handleCallSignal(d){if(d.action==="offer")return handleIncomingCall(d);if(d.action==="answer"&&pc)await pc.setRemoteDescription(d.answer);else if(d.action==="candidate"&&pc){try{await pc.addIceCandidate(d.candidate)}catch{}}else if(d.action==="hangup")hangup(false)}
function hangup(send=true){if(send&&ws&&activeChat?.other?.id)ws.send(JSON.stringify({type:"call",action:"hangup",to_user_id:activeChat.other.id}));if(pc){pc.close();pc=null}if(localStream){localStream.getTracks().forEach(t=>t.stop());localStream=null}$("remoteVideo").srcObject=null;$("localVideo").srcObject=null;closeModal("callModal")}
window.addEventListener("load",()=>{if(localStorage.getItem("dark")==="true")document.body.classList.add("dark");boot()});
