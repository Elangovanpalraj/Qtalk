let currentUser = "";
let selectedContact = "";
let socket = null;
let onlineUsersList = [];
let typingTimeout = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

const contacts = ["Rahul", "Priya", "Kumar", "Alex"];

document.addEventListener('DOMContentLoaded', () => {
    const picker = document.querySelector('emoji-picker');
    if (picker) {
        picker.addEventListener('emoji-click', event => {
            const input = document.getElementById("message-input");
            if (input) input.value += event.detail.unicode;
        });
    }
});

function login() {
    const input = document.getElementById("username-input").value.trim();
    if (input) {
        currentUser = input;
        document.getElementById("login-modal").style.display = "none";
        document.getElementById("user-display").innerText = `👤 ${currentUser}`;
        connectWebSocket();
        renderContacts();
    }
}

function connectWebSocket() {
    socket = new WebSocket(`ws://${window.location.host}/ws/${currentUser}`);
    
    socket.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === "status_update") {
                onlineUsersList = data.online_users || [];
                renderContacts();
                updateHeaderStatus();
            } 
            else if (data.type === "typing") {
                if (data.sender === selectedContact) {
                    const indicator = document.getElementById("typing-indicator");
                    if (indicator) {
                        if (data.is_typing) {
                            indicator.innerText = `${data.sender} is typing...`;
                            indicator.style.display = "block";
                        } else {
                            indicator.style.display = "none";
                        }
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
            else if (data.type === "message") {
                if (data.sender === selectedContact || data.receiver === selectedContact) {
                    appendMessage(data);
                    
                    if (data.sender === selectedContact && socket && socket.readyState === WebSocket.OPEN) {
                        socket.send(JSON.stringify({ type: "read_ack", sender: selectedContact }));
                    }
                    if (data.sender !== currentUser) {
                        const notif = document.getElementById("notif-sound");
                        if (notif) notif.play().catch(() => {});
                    }
                }
            }
        } catch (e) {
            console.error("WebSocket Error:", e);
        }
    };
    
    socket.onclose = function () {
        setTimeout(connectWebSocket, 2000);
    };
}

function renderContacts() {
    const list = document.getElementById("contact-list");
    if (!list) return;
    
    const searchVal = document.getElementById("search-input") ? document.getElementById("search-input").value.toLowerCase() : "";
    list.innerHTML = "";
    
    contacts
        .filter(c => c !== currentUser && c.toLowerCase().includes(searchVal))
        .forEach(contact => {
            const isOnline = onlineUsersList.includes(contact);
            const div = document.createElement("div");
            div.className = `contact-item ${contact === selectedContact ? 'active' : ''}`;
            div.onclick = () => selectContact(contact);
            div.innerHTML = `
                <span>${contact}</span>
                <span class="dot ${isOnline ? 'online' : ''}"></span>
            `;
            list.appendChild(div);
        });
}

function filterContacts() { renderContacts(); }

async function selectContact(contact) {
    selectedContact = contact;
    const headerName = document.getElementById("active-user-name");
    if (headerName) headerName.innerText = contact;
    
    renderContacts();
    updateHeaderStatus();
    
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
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "read_ack", sender: selectedContact }));
    }
}

function updateHeaderStatus() {
    const status = document.getElementById("active-user-status");
    if (!status || !selectedContact) return;
    const isOnline = onlineUsersList.includes(selectedContact);
    status.innerText = isOnline ? "Online" : "Offline";
    status.style.color = isOnline ? "#10b981" : "#9ca3af";
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
    
    if (!selectedContact) {
        alert("முதலில் ஒரு Contact-ஐ கிளிக் செய்யவும்!");
        return;
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        alert("Server Connection துண்டிக்கப்பட்டுள்ளது. Page-ஐ Refresh செய்யவும்.");
        return;
    }
    
    if (msg || fileUrl) {
        const payload = {
            type: "message",
            receiver: selectedContact,
            message: msg,
            file_url: fileUrl
        };
        socket.send(JSON.stringify(payload));
        if (input) input.value = "";
        
        const emojiPicker = document.getElementById("emoji-picker-container");
        if (emojiPicker) emojiPicker.style.display = "none";
    }
}

function deleteMessage(msgId) {
    if (confirm("Delete message for everyone?")) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                type: "delete_msg",
                msg_id: msgId,
                receiver: selectedContact
            }));
        }
    }
}

function appendMessage(data) {
    const container = document.getElementById("messages-container");
    if (!container) return;
    
    const div = document.createElement("div");
    const isSent = data.sender === currentUser;
    
    div.className = `message ${isSent ? 'sent' : 'received'}`;
    div.id = `msg-${data.id}`;
    
    let content = data.message ? `<p class="msg-text">${data.message}</p>` : "";
    
    if (data.file_url) {
        if (data.file_url.match(/\.(jpeg|jpg|gif|png)$/i)) {
            content += `<img src="${data.file_url}" alt="image" />`;
        } else if (data.file_url.match(/\.(webm|mp3|wav|ogg)$/i)) {
            content += `<audio controls src="${data.file_url}"></audio>`;
        } else {
            content += `<a href="${data.file_url}" target="_blank" style="color:white;">📎 Attached File</a>`;
        }
    }
    
    let tickHtml = "";
    if (isSent) {
        if (data.is_read) {
            tickHtml = `<span class="tick double read">✓✓</span>`;
        } else {
            tickHtml = `<span class="tick single">✓</span>`;
        }
    }
    let deleteBtn = isSent ? `<i class="fa-solid fa-trash delete-btn" onclick="deleteMessage(${data.id})"></i>` : "";
    content += `<div class="msg-footer">${deleteBtn} <span class="time">${data.timestamp}</span> ${tickHtml}</div>`;
    
    div.innerHTML = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function searchMessages() {
    const query = document.getElementById("msg-search-input").value.toLowerCase();
    const messages = document.querySelectorAll(".message");
    messages.forEach(msg => {
        const text = msg.querySelector(".msg-text") ? msg.querySelector(".msg-text").innerText.toLowerCase() : "";
        if (text.includes(query)) {
            msg.style.display = "block";
        } else {
            msg.style.display = "none";
        }
    });
}

async function toggleRecording() {
    const recordBtn = document.getElementById("record-btn");
    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append("file", audioBlob, "voice_note.webm");
                const response = await fetch("/upload", { method: "POST", body: formData });
                const result = await response.json();
                sendMessage(result.file_url);
            };
            mediaRecorder.start();
            isRecording = true;
            if (recordBtn) recordBtn.style.color = "#ef4444";
        } catch (err) {
            alert("Microphone Access Denied!");
        }
    } else {
        if (mediaRecorder) mediaRecorder.stop();
        isRecording = false;
        if (recordBtn) recordBtn.style.color = "var(--accent)";
    }
}

function handleKeyPress(e) { 
    if (e.key === "Enter") {
        e.preventDefault();
        sendMessage(); 
    }
}

async function uploadFile() {
    const fileInput = document.getElementById("file-upload");
    if (!fileInput || fileInput.files.length === 0) return;
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    const response = await fetch("/upload", { method: "POST", body: formData });
    const result = await response.json();
    sendMessage(result.file_url);
}

function toggleEmojiPicker() {
    const container = document.getElementById("emoji-picker-container");
    if (container) {
        container.style.display = container.style.display === "none" ? "block" : "none";
    }
}

function toggleTheme() { 
    document.body.classList.toggle("light-theme"); 
}
