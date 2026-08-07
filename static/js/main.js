let currentUserPhone = "";
let selectedUser = "";
let selectedGroupId = null;
let socket = null;
let typingTimeout = null;
let replyMessageId = null;
let mediaRecorder = null;
let audioChunks = [];

// E2EE Dynamic Key Generator per session
let sharedCryptoKey = null;

// 🔒 Crypto Key Generator (AES-GCM 256-bit)
async function getOrCreateCryptoKey() {
    if (sharedCryptoKey) return sharedCryptoKey;
    sharedCryptoKey = await window.crypto.subtle.generateKey(
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
    );
    return sharedCryptoKey;
}

// 🟢 A. Encryption Helper Function (பூட்ட)
async function encryptMessage(plaintext, secretKey) {
    const enc = new TextEncoder();
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const encodedMessage = enc.encode(plaintext);

    const ciphertext = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: iv },
        secretKey,
        encodedMessage
    );

    return {
        ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
        iv: btoa(String.fromCharCode(...iv))
    };
}

// 🟢 B. Decryption Helper Function (திறக்க)
async function decryptMessage(encryptedObj, secretKey) {
    try {
        const ciphertext = Uint8Array.from(atob(encryptedObj.ciphertext), c => c.charCodeAt(0));
        const iv = Uint8Array.from(atob(encryptedObj.iv), c => c.charCodeAt(0));

        const decrypted = await window.crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            secretKey,
            ciphertext
        );

        return new TextDecoder().decode(decrypted);
    } catch (e) {
        return "[Decryption Failed / Plaintext Message]";
    }
}

// 🟢 1. Verify OTP & Login
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
    
    await getOrCreateCryptoKey();
    connectWebSocket();
    loadContactsAndGroups();
}

// 🟢 2. Real-Time WebSocket Listener
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUserPhone}`);

    socket.onmessage = async function(event) {
        const data = JSON.parse(event.data);

        // A. Handle Incoming Messages
        if (data.type === "new_message") {
            if (data.sender === selectedUser || data.receiver === selectedUser || data.group_id === selectedGroupId) {
                // Try Decrypting if Encrypted Payload
                if (data.content && data.content.startsWith("{")) {
                    try {
                        const parsedContent = JSON.parse(data.content);
                        if (parsedContent.ciphertext) {
                            data.content = await decryptMessage(parsedContent, sharedCryptoKey);
                        }
                    } catch (e) { /* Keep original content if not E2EE JSON */ }
                }

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
                    tickElem.style.color = "#53bdeb";
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

// 🟢 4. Encrypted Send Message Function
async function sendMessage(msgType = "text", fileUrl = null) {
    const input = document.getElementById("messageInput");
    const plainText = input ? input.value.trim() : "";

    if (!plainText && !fileUrl) return;

    let payloadContent = plainText;

    // Encrypt Plaintext for E2EE
    if (plainText) {
        const key = await getOrCreateCryptoKey();
        const encryptedData = await encryptMessage(plainText, key);
        payloadContent = JSON.stringify(encryptedData);
    }

    const payload = {
        type: "message",
        receiver: selectedUser,
        group_id: selectedGroupId,
        msg_type: msgType,
        content: payloadContent,
        file_url: fileUrl,
        reply_to_id: replyMessageId
    };

    socket.send(JSON.stringify(payload));
    
    // UI Local Echo
    appendMessageToUI({
        id: Date.now(),
        sender: currentUserPhone,
        content: plainText,
        file_url: fileUrl,
        msg_type: msgType,
        status: "sent",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });

    if (input) input.value = "";
    replyMessageId = null;
}

// 🟢 5. Voice Recorder Integration
async function startVoiceRecording() {
    try {
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
    } catch (err) {
        alert("Microphone access required for voice notes!");
    }
}

function stopVoiceRecording() {
    if (mediaRecorder) mediaRecorder.stop();
}

// 🟢 6. Message UI Renderer
function appendMessageToUI(msg) {
    const chatBox = document.getElementById("chatBox");
    if (!chatBox) return;

    const isOutgoing = msg.sender === currentUserPhone;
    const msgDiv = document.createElement("div");
    msgDiv.id = `msg-${msg.id}`;
    msgDiv.className = `message-bubble ${isOutgoing ? "outgoing" : "incoming"}`;

    let tickHtml = "";
    if (isOutgoing) {
        let tickColor = msg.status === "read" ? "#53bdeb" : "#8696a0";
        let tickSymbol = msg.status === "sent" ? "✓" : "✓✓";
        tickHtml = `<span id="tick-${msg.id}" class="msg-tick" style="color:${tickColor}; margin-left:5px;">${tickSymbol}</span>`;
    }

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
            <span class="msg-time">${msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            ${tickHtml}
        </div>
        <button onclick="reactToMessage(${msg.id}, '❤️')" class="react-btn">❤️</button>
        <button onclick="reactToMessage(${msg.id}, '👍')" class="react-btn">👍</button>
    `;

    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// 🟢 7. React to Message
function reactToMessage(msgId, emoji) {
    socket.send(JSON.stringify({
        type: "reaction",
        message_id: msgId,
        emoji: emoji,
        receiver: selectedUser
    }));
}

// Load Contacts Helper
async function loadContactsAndGroups() {
    try {
        const res = await fetch(`/contacts/${currentUserPhone}`);
        const contacts = await res.json();
        const list = document.getElementById("userList");
        if (!list) return;
        list.innerHTML = "";

        contacts.forEach(c => {
            const li = document.createElement("li");
            li.className = "contact-item";
            li.innerHTML = `
                <div class="contact-avatar"><img src="https://ui-avatars.com/api/?name=${encodeURIComponent(c.name)}&background=00a884&color=fff"></div>
                <div class="contact-info">
                    <div class="contact-top"><span>${c.name}</span></div>
                    <div class="contact-bottom"><span>${c.phone}</span></div>
                </div>
            `;
            li.onclick = () => {
                selectedUser = c.phone;
                selectedGroupId = null;
                document.getElementById("chatWithTitle").innerText = c.name;
                document.getElementById("chatStatusText").innerText = c.phone;
            };
            list.appendChild(li);
        });
    } catch (err) { console.error(err); }
}
