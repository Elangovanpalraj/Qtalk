let currentUser = "";
let selectedContact = "";
let isGroupChat = false;
let socket = null;
let onlineUsersList = [];
let typingTimeout = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let replyingToMsg = null;
let recTimerInterval = null;
let recSeconds = 0;
let currentPlayingAudio = null;

// Dynamic Contacts Management
let contacts = [];
let groups = ["Developers Hub", "Tech Squad"];
let unreadCounts = {};
let lastMessages = {};

// WebRTC Configuration
let peerConnection = null;
let localStream = null;
const rtcConfig = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };

document.addEventListener('DOMContentLoaded', () => {
    const picker = document.querySelector('emoji-picker');
    if (picker) {
        picker.addEventListener('emoji-click', event => {
            const input = document.getElementById("message-input");
            if (input) input.value += event.detail.unicode;
        });
    }

    const dropZone = document.getElementById("messages-container");
    if (dropZone) {
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("drag-over");
        });

        dropZone.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
        });

        dropZone.addEventListener("drop", async (e) => {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                const file = e.dataTransfer.files[0];
                await handleFileUpload(file);
            }
        });
    }
});

function login() {
    const input = document.getElementById("username-input").value.trim();
    if (input) {
        currentUser = input;
        document.getElementById("login-modal").style.display = "none";
        document.getElementById("user-display").innerText = `👤 ${currentUser}`;
        document.getElementById("app-container").style.display = "flex";

        connectWebSocket();
        fetchInitialUsers();
    }
}

async function fetchInitialUsers() {
    try {
        const res = await fetch("/users");
        if (res.ok) {
            const data = await res.json();
            data.users.forEach(u => {
                if (u !== currentUser && !contacts.includes(u)) {
                    contacts.push(u);
                }
            });
            renderContacts();
        }
    } catch (err) {
        console.error("Fetch Users Error:", err);
    }
}

function addNewContactModal() {
    const person = prompt("Enter contact name or phone number:");
    if (person && person.trim() !== "") {
        const target = person.trim();
        if (target === currentUser) return alert("You cannot add yourself!");
        if (!contacts.includes(target)) {
            contacts.push(target);
            renderContacts();
            selectContact(target, false);
        }
    }
}

async function syncPhoneContacts() {
    const props = ['name', 'tel'];
    const opts = { multiple: true };

    if ('contacts' in navigator && 'ContactsManager' in window) {
        try {
            const selectedContacts = await navigator.contacts.select(props, opts);
            if (selectedContacts.length > 0) {
                let addedCount = 0;
                selectedContacts.forEach(c => {
                    const cName = (c.name && c.name[0]) ? c.name[0] : ((c.tel && c.tel[0]) ? c.tel[0] : null);
                    if (cName && !contacts.includes(cName) && cName !== currentUser) {
                        contacts.push(cName);
                        addedCount++;
                    }
                });
                renderContacts();
                alert(`${addedCount} Contacts synced successfully!`);
            }
        } catch (err) {
            console.error("Contacts sync failed:", err);
        }
    } else {
        alert("Mobile Contact Picker API supported only on mobile devices/Chrome Android. Use the '+' button to add manually!");
    }
}

/* Dynamic WebSocket Protocol for SSL/Localtunnel */
function connectWebSocket() {
    if (!currentUser) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${currentUser}`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = function () {
        console.log("WebSocket Connected successfully via:", wsUrl);
    };

    socket.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === "status_update") {
                onlineUsersList = data.online_users || [];
                if (data.all_users) {
                    data.all_users.forEach(u => {
                        if (u !== currentUser && !contacts.includes(u)) {
                            contacts.push(u);
                        }
                    });
                }
                renderContacts();
                updateHeaderStatus();
            } 
            else if (data.type === "typing") {
                if (data.sender === selectedContact) {
                    const indicator = document.getElementById("typing-indicator");
                    if (indicator) {
                        indicator.innerText = `${data.sender} is typing...`;
                        indicator.style.display = data.is_typing ? "inline" : "none";
                    }
                }
            } 
            else if (data.type === "read_ack") {
                document.querySelectorAll('.tick').forEach(tick => {
                    tick.className = "tick double read";
                    tick.innerText = "✓✓";
                });
            }
            else if (data.type === "delete_msg") {
                const el = document.getElementById(`msg-${data.msg_id}`);
                if (el) el.remove();
            }
            else if (data.type === "reaction") {
                const msgEl = document.getElementById(`msg-${data.msg_id}`);
                if (msgEl) {
                    let rxnContainer = msgEl.querySelector('.msg-reactions');
                    if (!rxnContainer) {
                        rxnContainer = document.createElement('div');
                        rxnContainer.className = 'msg-reactions';
                        msgEl.appendChild(rxnContainer);
                    }
                    rxnContainer.innerText = data.emoji;
                }
            }
            else if (data.type === "message") {
                const partner = data.sender === currentUser ? data.receiver : data.sender;
                
                if (!contacts.includes(partner) && partner !== currentUser) {
                    contacts.push(partner);
                }

                lastMessages[partner] = data.message || (data.file_url ? "📎 Attachment" : "");
                
                if (partner !== selectedContact && data.sender !== currentUser) {
                    unreadCounts[partner] = (unreadCounts[partner] || 0) + 1;
                    showToastNotification(data.sender, data.message || "Sent an attachment");
                }

                if (data.sender === selectedContact || data.receiver === selectedContact) {
                    appendMessage(data);
                    
                    if (data.sender === selectedContact && socket && socket.readyState === WebSocket.OPEN) {
                        socket.send(JSON.stringify({ type: "read_ack", sender: selectedContact }));
                    }

                    if (data.sender !== currentUser) {
                        document.getElementById("notif-sound")?.play().catch(() => {});
                    }
                }
                renderContacts();
            }
            else if (data.type === "call_offer") handleCallOffer(data);
            else if (data.type === "call_answer") handleCallAnswer(data);
            else if (data.type === "ice_candidate") handleIceCandidate(data);
            else if (data.type === "end_call") closeCallUI();

        } catch (e) {
            console.error("WS Message Error:", e);
        }
    };

    socket.onerror = function(err) {
        console.error("WebSocket Error:", err);
    };

    socket.onclose = function () {
        console.log("WebSocket Disconnected. Reconnecting...");
        setTimeout(() => { if (currentUser) connectWebSocket(); }, 1000);
    };
}

function showToastNotification(sender, message) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.style.cssText = "position: fixed; top: 20px; right: 20px; z-index: 9999;";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = "toast-notification";
    toast.style.cssText = "background: #1e293b; color: #fff; padding: 12px 18px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); border-left: 4px solid #6366f1; cursor: pointer; transition: all 0.3s ease;";
    toast.innerHTML = `<strong>${sender}</strong><br><small style="color: #94a3b8;">${message.substring(0, 35)}...</small>`;

    toast.onclick = () => {
        selectContact(sender, false);
        toast.remove();
    };

    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 4000);
}

function renderContacts() {
    const list = document.getElementById("contact-list");
    if (!list) return;
    
    const searchVal = document.getElementById("search-input")?.value.toLowerCase() || "";
    list.innerHTML = "";
    
    groups.filter(g => g.toLowerCase().includes(searchVal)).forEach(group => {
        const div = document.createElement("div");
        div.className = `contact-item ${group === selectedContact ? 'active' : ''}`;
        div.onclick = () => selectContact(group, true);
        div.innerHTML = `
            <div class="contact-info">
                <span class="contact-name"><i class="fa-solid fa-users" style="color:#6366f1;"></i> ${group}</span>
                <span class="last-msg-preview">${lastMessages[group] || 'Group Chat'}</span>
            </div>
        `;
        list.appendChild(div);
    });

    contacts.filter(c => c !== currentUser && c.toLowerCase().includes(searchVal)).forEach(contact => {
        const isOnline = onlineUsersList.includes(contact);
        const unread = unreadCounts[contact] || 0;
        const div = document.createElement("div");
        div.className = `contact-item ${contact === selectedContact ? 'active' : ''}`;
        div.onclick = () => selectContact(contact, false);
        div.innerHTML = `
            <div class="contact-info">
                <span class="contact-name">${contact}</span>
                <span class="last-msg-preview">${lastMessages[contact] || 'No messages yet'}</span>
            </div>
            <div class="contact-meta">
                <span class="dot ${isOnline ? 'online' : ''}"></span>
                ${unread > 0 ? `<span class="unread-badge">${unread}</span>` : ''}
            </div>
        `;
        list.appendChild(div);
    });
}

function filterContacts() { renderContacts(); }

async function selectContact(target, isGroup = false) {
    selectedContact = target;
    isGroupChat = isGroup;
    unreadCounts[target] = 0;

    document.getElementById("active-user-name").innerText = target;
    document.getElementById("call-actions").style.display = isGroup ? "none" : "flex";
    
    renderContacts();
    updateHeaderStatus();

    // Mobile: switch from contact list to full-screen chat view
    if (window.innerWidth <= 768) {
        showChatAreaMobile();
    }
    
    try {
        const res = await fetch(`/messages/${currentUser}/${selectedContact}`);
        if (res.ok) {
            const messages = await res.json();
            const container = document.getElementById("messages-container");
            if (container) {
                container.innerHTML = "";
                messages.forEach(msg => appendMessage(msg));
            }
        }
    } catch (err) {
        console.error("Fetch Messages Error:", err);
    }

    if (socket && socket.readyState === WebSocket.OPEN && !isGroupChat) {
        socket.send(JSON.stringify({ type: "read_ack", sender: selectedContact }));
    }
}

/* ===== MOBILE NAVIGATION (added, does not affect existing desktop logic) ===== */
function showContactsList() {
    const chatArea = document.getElementById('chat-area');
    const sidebar = document.getElementById('sidebar');
    if (chatArea) chatArea.classList.remove('mobile-active');
    if (sidebar) sidebar.classList.remove('mobile-hidden');
}

function showChatAreaMobile() {
    const chatArea = document.getElementById('chat-area');
    const sidebar = document.getElementById('sidebar');
    if (chatArea) chatArea.classList.add('mobile-active');
    if (sidebar) sidebar.classList.add('mobile-hidden');
}

function updateHeaderStatus() {
    const status = document.getElementById("active-user-status");
    if (!status || !selectedContact) return;
    if (isGroupChat) {
        status.innerText = "Group Room";
        status.style.color = "#f59e0b";
        return;
    }
    const isOnline = onlineUsersList.includes(selectedContact);
    status.innerText = isOnline ? "Online" : "Offline";
    status.style.color = isOnline ? "#10b981" : "#9ca3af";
}

function openGroupModal() { document.getElementById("group-modal").style.display = "flex"; }
function closeGroupModal() { document.getElementById("group-modal").style.display = "none"; }
function createGroup() {
    const name = document.getElementById("group-name-input").value.trim();
    if (name && !groups.includes(name)) {
        groups.push(name);
        closeGroupModal();
        renderContacts();
        selectContact(name, true);
    }
}

function sendTypingStatus() {
    if (!selectedContact || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "typing", receiver: selectedContact, is_typing: true }));

    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "typing", receiver: selectedContact, is_typing: false }));
        }
    }, 2000);
}

function sendMessage(fileUrl = "") {
    const input = document.getElementById("message-input");
    const msg = input ? input.value.trim() : "";
    
    if (!selectedContact) return alert("Select a contact or group first!");

    if (msg || fileUrl) {
        const payload = {
            type: "message",
            receiver: selectedContact,
            message: msg,
            file_url: fileUrl,
            reply_to: replyingToMsg ? replyingToMsg.text : null
        };
        socket.send(JSON.stringify(payload));
        if (input) input.value = "";
        
        cancelReply();
        document.getElementById("emoji-picker-container").style.display = "none";
        socket.send(JSON.stringify({ type: "typing", receiver: selectedContact, is_typing: false }));
    }
}

function setReply(sender, text) {
    replyingToMsg = { sender, text };
    document.getElementById("reply-to-user").innerText = `Replying to ${sender}`;
    document.getElementById("reply-to-text").innerText = text;
    document.getElementById("reply-preview-box").style.display = "flex";
}

function cancelReply() {
    replyingToMsg = null;
    document.getElementById("reply-preview-box").style.display = "none";
}

function sendReaction(msgId, emoji) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: "reaction",
            msg_id: msgId,
            emoji: emoji,
            receiver: selectedContact
        }));
    }
}

function deleteMessage(msgId) {
    if (confirm("Delete message for everyone?") && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "delete_msg", msg_id: msgId, receiver: selectedContact }));
    }
}

function appendMessage(data) {
    const container = document.getElementById("messages-container");
    if (!container) return;

    const div = document.createElement("div");
    const isSent = data.sender === currentUser;
    
    div.className = `message ${isSent ? 'sent' : 'received'}`;
    div.id = `msg-${data.id}`;
    
    let content = `
        <div class="reaction-bar">
            <span onclick="sendReaction(${data.id}, '❤️')">❤️</span>
            <span onclick="sendReaction(${data.id}, '👍')">👍</span>
            <span onclick="sendReaction(${data.id}, '😂')">😂</span>
            <span onclick="sendReaction(${data.id}, '🔥')">🔥</span>
        </div>
    `;

    if (isGroupChat && !isSent && data.sender) {
        content += `<div class="group-sender-badge" style="font-size:11px; font-weight:bold; color:#6366f1; margin-bottom:3px;">${data.sender}</div>`;
    }

    if (data.reply_to) {
        content += `<div class="quoted-reply"><span class="q-user">Replying:</span>${data.reply_to}</div>`;
    }
    
    if (data.message && data.message.trim() !== "") {
        let parsedText = (typeof marked !== 'undefined') ? marked.parse(data.message) : data.message;
        content += `<div class="msg-text">${parsedText}</div>`;
    }
    
    if (data.file_url) {
        if (data.file_url.match(/\.(jpeg|jpg|gif|png)$/i)) {
            content += `<img src="${data.file_url}" alt="image" onclick="openLightbox('${data.file_url}')" style="cursor:pointer;" />`;
        } else if (data.file_url.match(/\.(webm|mp3|wav|ogg)$/i)) {
            content += `
                <div class="custom-audio-player">
                    <button class="audio-play-btn" onclick="toggleAudioPlay(this, '${data.file_url}')">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    <div class="audio-waveform-mock"><div class="audio-progress"></div></div>
                    <span class="audio-time">Voice</span>
                </div>
            `;
        } else {
            const fileName = data.file_url.split('/').pop() || "Document";
            content += `
                <div class="document-preview-card" style="display:flex; align-items:center; gap:10px; background:rgba(255,255,255,0.08); padding:8px 12px; border-radius:8px; margin-top:5px;">
                    <i class="fa-solid fa-file-lines" style="font-size:24px; color:#38bdf8;"></i>
                    <div style="flex:1; overflow:hidden;">
                        <div style="font-size:13px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${fileName}</div>
                        <a href="${data.file_url}" target="_blank" style="font-size:11px; color:#38bdf8; text-decoration:underline;">Download File</a>
                    </div>
                </div>
            `;
        }
    }

    let tickHtml = "";
    if (isSent) {
        const isOnline = onlineUsersList.includes(selectedContact);
        tickHtml = data.is_read ? `<span class="tick double read">✓✓</span>` : (isOnline ? `<span class="tick double">✓✓</span>` : `<span class="tick single">✓</span>`);
    }

    let deleteBtn = isSent ? `<i class="fa-solid fa-trash delete-btn" onclick="deleteMessage(${data.id})"></i>` : "";
    let replyBtn = `<i class="fa-solid fa-reply reply-action-btn" onclick="setReply('${data.sender}', '${data.message || 'Attachment'}')"></i>`;

    content += `<div class="msg-footer">${replyBtn} ${deleteBtn} <span class="time">${data.timestamp || ''}</span> ${tickHtml}</div>`;
    
    div.innerHTML = content;
    container.appendChild(div);

    if (typeof Prism !== 'undefined') {
        Prism.highlightAllUnder(div);
    }

    container.scrollTop = container.scrollHeight;
}

function searchMessages() {
    const query = document.getElementById("msg-search-input")?.value.trim().toLowerCase() || "";
    
    document.querySelectorAll(".message").forEach(msg => {
        const textNode = msg.querySelector(".msg-text");
        if (textNode) {
            const rawText = textNode.textContent;
            if (query && rawText.toLowerCase().includes(query)) {
                msg.style.display = "flex";
                const regex = new RegExp(`(${query})`, 'gi');
                textNode.innerHTML = rawText.replace(regex, '<mark class="highlight">$1</mark>');
            } else if (query) {
                msg.style.display = "none";
            } else {
                msg.style.display = "flex";
                textNode.innerHTML = rawText;
            }
        }
    });
}

async function toggleRecording() {
    const recordBtn = document.getElementById("record-btn");
    const recStatusBox = document.getElementById("recording-status");
    const msgInput = document.getElementById("message-input");

    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                await handleFileUpload(audioBlob, "voice_note.webm");
            };

            mediaRecorder.start();
            isRecording = true;
            
            if (recordBtn) recordBtn.style.color = "#ef4444";
            if (recStatusBox) recStatusBox.style.display = "flex";
            if (msgInput) msgInput.style.display = "none";

            recSeconds = 0;
            recTimerInterval = setInterval(() => {
                recSeconds++;
                const mins = String(Math.floor(recSeconds / 60)).padStart(2, '0');
                const secs = String(recSeconds % 60).padStart(2, '0');
                document.getElementById("rec-timer").innerText = `${mins}:${secs}`;
            }, 1000);

        } catch (err) {
            alert("Microphone Access Denied!");
        }
    } else {
        if (mediaRecorder) mediaRecorder.stop();
        isRecording = false;

        if (recordBtn) recordBtn.style.color = "var(--accent)";
        if (recStatusBox) recStatusBox.style.display = "none";
        if (msgInput) msgInput.style.display = "block";
        
        clearInterval(recTimerInterval);
        document.getElementById("rec-timer").innerText = "00:00";
    }
}

function toggleAudioPlay(btn, audioUrl) {
    const icon = btn.querySelector("i");
    
    if (currentPlayingAudio && currentPlayingAudio.src === audioUrl && !currentPlayingAudio.paused) {
        currentPlayingAudio.pause();
        icon.className = "fa-solid fa-play";
    } else {
        if (currentPlayingAudio) currentPlayingAudio.pause();
        
        currentPlayingAudio = new Audio(audioUrl);
        currentPlayingAudio.play();
        icon.className = "fa-solid fa-pause";

        currentPlayingAudio.onended = () => {
            icon.className = "fa-solid fa-play";
        };
    }
}

function handleKeyPress(e) { if (e.key === "Enter") { e.preventDefault(); sendMessage(); } }

async function handleFileUpload(fileObj, filename = null) {
    const formData = new FormData();
    formData.append("file", fileObj, filename || fileObj.name);
    try {
        const response = await fetch("/upload", { method: "POST", body: formData });
        const result = await response.json();
        sendMessage(result.file_url);
    } catch (err) {
        console.error("Upload failed:", err);
    }
}

async function uploadFile() {
    const fileInput = document.getElementById("file-upload");
    if (!fileInput || fileInput.files.length === 0) return;
    await handleFileUpload(fileInput.files[0]);
}

function toggleEmojiPicker() {
    const container = document.getElementById("emoji-picker-container");
    if (container) container.style.display = container.style.display === "none" ? "block" : "none";
}

function toggleTheme() { 
    document.body.classList.toggle("light-theme"); 
    const themeIcon = document.getElementById("theme-icon");
    if (themeIcon) {
        themeIcon.className = document.body.classList.contains("light-theme") ? "fa-solid fa-moon" : "fa-solid fa-sun";
    }
}

function openLightbox(imgUrl) {
    const modal = document.getElementById("lightbox-modal");
    const img = document.getElementById("lightbox-img");
    const downloadBtn = document.getElementById("download-img-btn");
    
    img.src = imgUrl;
    downloadBtn.href = imgUrl;
    modal.style.display = "flex";
}

function closeLightbox() {
    document.getElementById("lightbox-modal").style.display = "none";
}

/* Dropdown Menu Toggle Handler */
function toggleMenu() {
    const dropdown = document.getElementById("chat-dropdown-menu");
    if (dropdown) dropdown.classList.toggle("show");
}

window.onclick = function(event) {
    if (!event.target.matches('.fa-ellipsis-vertical') && !event.target.closest('.dropdown')) {
        const dropdowns = document.getElementsByClassName("dropdown-content");
        for (let i = 0; i < dropdowns.length; i++) {
            const openDropdown = dropdowns[i];
            if (openDropdown.classList.contains('show')) {
                openDropdown.classList.remove('show');
            }
        }
    }
}

function clearCurrentChat() {
    if (confirm("Are you sure you want to clear this chat?")) {
        const container = document.getElementById("messages-container");
        if (container) container.innerHTML = "";
    }
}

/* WebRTC Calls */
async function startCall(type) {
    if (!selectedContact) return alert("Select a contact to call!");
    document.getElementById("call-modal").style.display = "flex";
    document.getElementById("call-status-text").innerText = `Calling ${selectedContact}...`;

    try {
        localStream = await navigator.mediaDevices.getUserMedia({ video: type === 'video', audio: true });
        document.getElementById("local-video").srcObject = localStream;
        createPeerConnection();
        localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));

        const offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        socket.send(JSON.stringify({ type: "call_offer", receiver: selectedContact, offer: offer, callType: type }));
    } catch (err) {
        alert("Camera/Mic permission denied!");
        closeCallUI();
    }
}

async function handleCallOffer(data) {
    if (!confirm(`${data.sender} is calling you (${data.callType} call). Accept?`)) {
        socket.send(JSON.stringify({ type: "end_call", receiver: data.sender }));
        return;
    }
    selectedContact = data.sender;
    document.getElementById("call-modal").style.display = "flex";
    document.getElementById("call-status-text").innerText = `In Call with ${selectedContact}`;

    try {
        localStream = await navigator.mediaDevices.getUserMedia({ video: data.callType === 'video', audio: true });
        document.getElementById("local-video").srcObject = localStream;
        createPeerConnection();
        localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));

        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);

        socket.send(JSON.stringify({ type: "call_answer", receiver: data.sender, answer: answer }));
    } catch (err) {
        closeCallUI();
    }
}

async function handleCallAnswer(data) {
    document.getElementById("call-status-text").innerText = `Connected with ${selectedContact}`;
    if (peerConnection) await peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
}

function handleIceCandidate(data) {
    if (peerConnection && data.candidate) peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
}

function createPeerConnection() {
    peerConnection = new RTCPeerConnection(rtcConfig);
    peerConnection.onicecandidate = (event) => {
        if (event.candidate && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ice_candidate", receiver: selectedContact, candidate: event.candidate }));
        }
    };
    peerConnection.ontrack = (event) => {
        document.getElementById("remote-video").srcObject = event.streams[0];
    };
}

function endCall() {
    if (selectedContact && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "end_call", receiver: selectedContact }));
    }
    closeCallUI();
}

function closeCallUI() {
    document.getElementById("call-modal").style.display = "none";
    if (localStream) { 
        localStream.getTracks().forEach(track => track.stop()); 
        localStream = null; 
    }
    if (peerConnection) { 
        peerConnection.close(); 
        peerConnection = null; 
    }
}