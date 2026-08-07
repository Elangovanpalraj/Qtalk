let currentUserPhone = "";
let selectedUser = "";
let selectedGroupId = null;
let socket = null;
let typingTimeout = null;
let replyMessageId = null;
let mediaRecorder = null;
let audioChunks = [];

// 🟢 1. Verify OTP & Connect
async function verifyOTP() {
    const otp = document.getElementById("otpCode").value.trim();
    if (otp !== "123456") return alert("Invalid OTP code!");

    currentUserPhone = document.getElementById("userPhone").value.trim();

    await fetch("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: currentUserPhone, name: "User " + currentUserPhone.slice(-4) })
    });

    document.getElementById("loginScreen").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    
    connectWebSocket();
    loadContactsAndGroups();
}

// 🟢 2. Real-Time Engine (WebSocket)
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUserPhone}`);

    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);

        // A. Handle Incoming Messages
        if (data.type === "new_message") {
            if (data.sender === selectedUser || data.receiver === selectedUser || data.group_id === selectedGroupId) {
                appendMessageToUI(data);
                // Send Read Ack (Blue Tick Trigger)
                socket.send(JSON.stringify({ type: "mark_read", message_ids: [data.id], sender_phone: data.sender }));
            }
        }
        // B. Handle Typing Status
        else if (data.type === "typing" && data.sender === selectedUser) {
            const statusElem = document.getElementById("chatStatusText");
            if (statusElem) {
                statusElem.innerText = data.is_typing ? "typing..." : "online";
                statusElem.style.color = data.is_typing ? "#00a884" : "#8696a0";
            }
        }
        // C. Read Ack Updates (Blue Ticks)
        else if (data.type === "read_ack") {
            data.message_ids.forEach(id => {
                const tickElem = document.getElementById(`tick-${id}`);
                if (tickElem) {
                    tickElem.innerText = "✓✓";
                    tickElem.style.color = "#53bdeb"; // Blue tick
                }
            });
        }
        // D. Emoji Reaction Updates
        else if (data.type === "reaction") {
            const msgElem = document.getElementById(`msg-${data.message_id}`);
            if (msgElem) {
                let reactBox = msgElem.querySelector(".reaction-badge");
                if (!reactBox) {
                    reactBox = document.createElement("span");
                    reactBox.className = "reaction-badge";
                    msgElem.appendChild(reactBox);
                }
                reactBox.innerText = data.emoji;
            }
        }
    };
}

// 🟢 3. Typing Indicator Sender
function handleTypingInput() {
    if (!socket || !selectedUser) return;
    socket.send(JSON.stringify({ type: "typing", receiver: selectedUser, is_typing: true }));
    
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        socket.send(JSON.stringify({ type: "typing", receiver: selectedUser, is_typing: false }));
    }, 2000);
}

// 🟢 4. Send Message (Supports Text, Voice, File, Reply)
async function sendMessage(msgType = "text", fileUrl = null) {
    const input = document.getElementById("messageInput");
    const content = input ? input.value.trim() : "";

    if (!content && !fileUrl) return;

    const payload = {
        type: "message",
        receiver: selectedUser,
        group_id: selectedGroupId,
        msg_type: msgType,
        content: content,
        file_url: fileUrl,
        reply_to_id: replyMessageId
    };

    socket.send(JSON.stringify(payload));
    
    if (input) input.value = "";
    replyMessageId = null; // Reset quote reply
}

// 🟢 5. Voice Message Recorder Integration
async function startVoiceRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", audioBlob, "voice_note.webm");

        const res = await fetch("/upload", { method: "POST", body: formData });
        const data = await res.json();
        if (data.file_url) {
            sendMessage("voice", data.file_url);
        }
    };
    mediaRecorder.start();
}

function stopVoiceRecording() {
    if (mediaRecorder) mediaRecorder.stop();
}

// 🟢 6. Message UI Renderer (Status Ticks & Media Cards)
function appendMessageToUI(msg) {
    const chatBox = document.getElementById("chatBox");
    if (!chatBox) return;

    const isOutgoing = msg.sender === currentUserPhone;
    const msgDiv = document.createElement("div");
    msgDiv.id = `msg-${msg.id}`;
    msgDiv.className = `message-bubble ${isOutgoing ? "outgoing" : "incoming"}`;

    // Tick Icon Logic
    let tickHtml = "";
    if (isOutgoing) {
        let tickColor = msg.status === "read" ? "#53bdeb" : "#8696a0";
        let tickSymbol = msg.status === "sent" ? "✓" : "✓✓";
        tickHtml = `<span id="tick-${msg.id}" class="msg-tick" style="color:${tickColor}; margin-left:5px;">${tickSymbol}</span>`;
    }

    // Media Rendering Logic
    let bodyContent = `<div class="msg-text">${msg.content}</div>`;
    if (msg.msg_type === "image") {
        bodyContent = `<img src="${msg.file_url}" class="chat-img" /><div class="msg-text">${msg.content}</div>`;
    } else if (msg.msg_type === "voice") {
        bodyContent = `<audio controls src="${msg.file_url}"></audio>`;
    } else if (msg.msg_type === "document") {
        bodyContent = `<a href="${msg.file_url}" target="_blank" class="doc-link">📄 Download Document</a>`;
    }

    msgDiv.innerHTML = `
        ${msg.reply_to_id ? `<div class="quoted-reply">Replying to #${msg.reply_to_id}</div>` : ''}
        ${bodyContent}
        <div class="msg-meta">
            <span class="msg-time">${msg.timestamp}</span>
            ${tickHtml}
        </div>
        <button onclick="reactToMessage(${msg.id}, '❤️')" class="react-btn">❤️</button>
        <button onclick="reactToMessage(${msg.id}, '👍')" class="react-btn">👍</button>
    `;

    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// 🟢 7. React to Message (Emoji)
function reactToMessage(msgId, emoji) {
    socket.send(JSON.stringify({
        type: "reaction",
        message_id: msgId,
        emoji: emoji,
        receiver: selectedUser
    }));
}
