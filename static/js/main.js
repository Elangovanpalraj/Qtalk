let currentUser = "";
let selectedUser = "";
let socket = null;
let onlineUsers = [];
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

async function connectUser() {
    currentUser = document.getElementById("currentUser").value.trim();
    if (!currentUser) return alert("Enter your name or phone number!");

    // Update avatar text
    document.getElementById("navAvatar").src = `https://ui-avatars.com/api/?name=${currentUser}&background=0D8ABC&color=fff`;

    if (socket) socket.close();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUser}`);

    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.type === "status_update") {
            onlineUsers = data.online_users;
            loadUsers();
            updateChatHeaderStatus();
        } 
        else if (data.type === "message") {
            if (data.sender === selectedUser || data.sender === currentUser) {
                appendMessage(data.sender, data.message, data.file_url, data.timestamp, data.id);
            }
            if (data.sender !== currentUser) {
                document.getElementById("notifSound").play().catch(() => {});
            }
        }
    };

    loadUsers();
}

async function loadUsers() {
    try {
        const res = await fetch("/users");
        const users = await res.json();
        const list = document.getElementById("userList");
        list.innerHTML = "";
        
        users.forEach(u => {
            if(u.username !== currentUser && u.phone !== currentUser) {
                const li = document.createElement("li");
                li.className = `contact-item ${selectedUser === u.username ? 'active' : ''}`;
                
                const isOnline = onlineUsers.includes(u.username) || onlineUsers.includes(u.phone);
                const badgeClass = isOnline ? "online" : "offline";
                const avatarUrl = `https://ui-avatars.com/api/?name=${u.username}&background=random`;

                li.innerHTML = `
                    <div class="contact-avatar">
                        <img src="${avatarUrl}" alt="${u.username}">
                        <span class="badge ${badgeClass}"></span>
                    </div>
                    <div class="contact-info">
                        <div class="contact-top">
                            <span>${u.username}</span>
                            <span style="font-size:0.7rem; font-weight:normal; color:#8696a0;">12:45 PM</span>
                        </div>
                        <div class="contact-bottom">
                            <span class="last-msg">${isOnline ? 'Online' : 'Click to chat'}</span>
                        </div>
                    </div>
                `;
                li.onclick = () => selectContact(u.username);
                list.appendChild(list.contains(li) ? li : li);
            }
        });
    } catch (err) { console.error(err); }
}

async function selectContact(username) {
    selectedUser = username;
    
    // Toggle main chat view
    document.getElementById("emptyState").style.display = "none";
    document.getElementById("activeChatWrapper").style.display = "flex";

    document.getElementById("chatWithTitle").innerText = username;
    document.getElementById("activeAvatar").src = `https://ui-avatars.com/api/?name=${username}&background=random`;
    updateChatHeaderStatus();

    document.getElementById("chatBox").innerHTML = "";

    const res = await fetch(`/messages/${currentUser}/${selectedUser}`);
    const history = await res.json();
    history.forEach(m => appendMessage(m.sender, m.message, m.file_url, m.timestamp, m.id));
    
    loadUsers();
}

function updateChatHeaderStatus() {
    if (!selectedUser) return;
    const isOnline = onlineUsers.includes(selectedUser);
    document.getElementById("chatStatusText").innerText = isOnline ? "online" : "offline";
}

function sendMessage() {
    const input = document.getElementById("messageInput");
    const text = input.value.trim();

    if (!selectedUser) return alert("Select a contact first!");
    if (!text) return;

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: "message",
            receiver: selectedUser,
            message: text,
            file_url: ""
        }));
        input.value = "";
    }
}

function toggleAttachMenu() {
    const menu = document.getElementById("attachMenu");
    menu.style.display = menu.style.display === "flex" ? "none" : "flex";
}

function triggerFileInput() {
    document.getElementById("fileInput").click();
    document.getElementById("attachMenu").style.display = "none";
}

async function sendFile(event) {
    const file = event.target.files[0];
    if (!file || !selectedUser) return;

    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: "message",
            receiver: selectedUser,
            message: "",
            file_url: data.file_url
        }));
    }
    event.target.value = "";
}

async function toggleRecord() {
    const btn = document.getElementById("recordBtn");
    if (!selectedUser) return alert("Select a contact first!");

    if (!isRecording) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
            const file = new File([audioBlob], "voice_note.webm", { type: "audio/webm" });
            
            const formData = new FormData();
            formData.append("file", file);

            const res = await fetch("/upload", { method: "POST", body: formData });
            const data = await res.json();

            socket.send(JSON.stringify({
                type: "message",
                receiver: selectedUser,
                message: "",
                file_url: data.file_url
            }));
        };

        mediaRecorder.start();
        isRecording = true;
        btn.style.color = "#ef4444";
    } else {
        mediaRecorder.stop();
        isRecording = false;
        btn.style.color = "#aebac1";
    }
}

function appendMessage(sender, text, fileUrl, timestamp, msgId) {
    const box = document.getElementById("chatBox");
    const div = document.createElement("div");
    const isSent = sender === currentUser;
    div.classList.add("msg", isSent ? "sent" : "received");
    if (msgId) div.id = `msg-${msgId}`;

    let content = "";
    if (text) content += `<div>${text}</div>`;
    
    if (fileUrl) {
        if (fileUrl.endsWith(".webm") || fileUrl.endsWith(".mp3") || fileUrl.endsWith(".wav")) {
            content += `<audio controls src="${fileUrl}"></audio>`;
        } else if (fileUrl.match(/\.(jpeg|jpg|gif|png|webp)$/i)) {
            content += `<img src="${fileUrl}" alt="image" />`;
        } else {
            content += `<a href="${fileUrl}" target="_blank" style="color: #00a884;">📄 View Document</a>`;
        }
    }

    const timeStr = timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    content += `<div class="msg-meta">
                    <span>${timeStr}</span>
                    ${isSent ? '<i class="fa-solid fa-check-double blue-tick"></i>' : ''}
                </div>`;

    div.innerHTML = content;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

function toggleChatMenu() {
    const dropdown = document.getElementById("chatDropdown");
    dropdown.style.display = dropdown.style.display === "block" ? "none" : "block";
}

function toggleTheme() {
    document.body.classList.toggle("light-mode");
}

function handleKeyPress(e) {
    if (e.key === 'Enter') sendMessage();
}

window.onload = loadUsers;