// 🟢 Global State Variables
let currentUserPhone = "";
let selectedUser = "";
let selectedGroupId = null;
let socket = null;
let typingTimeout = null;
let replyMessageId = null;
let mediaRecorder = null;
let audioChunks = [];
let sharedCryptoKey = null;
let unreadCounts = {}; // Track unread messages per user

// 🔔 Request Browser Notification Permission on Load
if ("Notification" in window && Notification.permission !== "granted") {
    Notification.requestPermission();
}

// 🔒 1. End-to-End Encryption (E2EE) Helpers
async function getOrCreateCryptoKey() {
    if (sharedCryptoKey) return sharedCryptoKey;
    try {
        sharedCryptoKey = await window.crypto.subtle.generateKey(
            { name: "AES-GCM", length: 256 },
            true,
            ["encrypt", "decrypt"]
        );
    } catch (e) {
        console.warn("Crypto key creation fallback:", e);
    }
    return sharedCryptoKey;
}

async function encryptMessage(plaintext, secretKey) {
    if (!secretKey) return plaintext;
    try {
        const enc = new TextEncoder();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const encodedMessage = enc.encode(plaintext);

        const ciphertext = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            secretKey,
            encodedMessage
        );

        return JSON.stringify({
            ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertext))),
            iv: btoa(String.fromCharCode(...iv))
        });
    } catch (e) {
        return plaintext;
    }
}

async function decryptMessage(encryptedStr, secretKey) {
    if (!secretKey || !encryptedStr || typeof encryptedStr !== 'string' || !encryptedStr.startsWith("{")) return encryptedStr;
    try {
        const encryptedObj = JSON.parse(encryptedStr);
        if (!encryptedObj.ciphertext || !encryptedObj.iv) return encryptedStr;

        const ciphertext = Uint8Array.from(atob(encryptedObj.ciphertext), c => c.charCodeAt(0));
        const iv = Uint8Array.from(atob(encryptedObj.iv), c => c.charCodeAt(0));

        const decrypted = await window.crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            secretKey,
            ciphertext
        );

        return new TextDecoder().decode(decrypted);
    } catch (e) {
        return encryptedStr;
    }
}

// 🟢 2. Authentication & OTP
function sendOTP() {
    const phoneInput = document.getElementById("userPhone");
    const phone = phoneInput ? phoneInput.value.trim() : "";

    if (!phone || phone.length < 10) {
        alert("Please enter a valid phone number (at least 10 digits)");
        return;
    }

    currentUserPhone = phone;
    document.getElementById("phoneStep").style.display = "none";
    document.getElementById("otpStep").style.display = "block";
    alert("OTP Sent successfully! (Default code: 123456)");
}

async function verifyOTP() {
    const otpInput = document.getElementById("otpCode");
    const otp = otpInput ? otpInput.value.trim() : "";

    if (otp !== "123456") return alert("Invalid OTP code! (Use 123456)");

    try {
        await fetch("/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone: currentUserPhone, name: "User " + currentUserPhone.slice(-4) })
        });
    } catch (err) {
        console.error("Registration error:", err);
    }

    const navAvatar = document.getElementById("navAvatar");
    if (navAvatar) {
        navAvatar.src = `https://ui-avatars.com/api/?name=${currentUserPhone.slice(-4)}&background=00a884&color=fff`;
    }

    document.getElementById("loginScreen").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";

    await getOrCreateCryptoKey();
    connectWebSocket();
    loadContactsAndGroups();
    setupSearchFilter();
}

// 🟢 3. Real-Time WebSocket Client
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUserPhone}`);

    socket.onmessage = async function(event) {
        const data = JSON.parse(event.data);

        if (data.type === "new_message") {
            const isCurrentChat = (
                data.sender === selectedUser || 
                data.receiver === selectedUser || 
                (data.group_id && data.group_id === selectedGroupId)
            );

            // Decrypt incoming encrypted string if available
            if (data.content) {
                data.content = await decryptMessage(data.content, sharedCryptoKey);
            }

            if (isCurrentChat) {
                appendMessageToUI(data);
                // Auto mark as read if the sender is open
                if (data.sender === selectedUser) {
                    socket.send(JSON.stringify({ type: "mark_read", message_ids: [data.id], sender_phone: data.sender }));
                }
            } else {
                // Update Unread Badge Count
                const sender = data.sender;
                unreadCounts[sender] = (unreadCounts[sender] || 0) + 1;
                updateUnreadBadgeUI(sender);

                // Desktop Notification Trigger
                if (Notification.permission === "granted") {
                    new Notification(`New message from ${data.sender}`, {
                        body: data.content || "Sent a media file",
                        icon: "https://ui-avatars.com/api/?name=" + data.sender
                    });
                }
            }
        }
        else if (data.type === "typing" && data.sender === selectedUser) {
            const statusElem = document.getElementById("chatStatusText");
            if (statusElem) {
                statusElem.innerText = data.is_typing ? "typing..." : "Online";
                statusElem.style.color = data.is_typing ? "#00a884" : "#8696a0";
            }
        }
        else if (data.type === "read_ack") {
            if (data.message_ids) {
                data.message_ids.forEach(id => {
                    const tickElem = document.getElementById(`tick-${id}`);
                    if (tickElem) {
                        tickElem.innerHTML = '<i class="fa-solid fa-check-double" style="color:#53bdeb;"></i>';
                    }
                });
            }
        }
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

// 🟢 4. Message Inputs & Dispatcher
function handleKeyPress(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
}

function handleTypingInput() {
    if (!socket || !selectedUser) return;
    socket.send(JSON.stringify({ type: "typing", receiver: selectedUser, is_typing: true }));

    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        socket.send(JSON.stringify({ type: "typing", receiver: selectedUser, is_typing: false }));
    }, 2000);
}

async function sendMessage(msgType = "text", fileUrl = null) {
    const input = document.getElementById("messageInput");
    const plainText = input ? input.value.trim() : "";

    if (!plainText && !fileUrl) return;
    if (!selectedUser && !selectedGroupId) {
        alert("Please select a contact or group to send a message!");
        return;
    }

    let payloadContent = plainText;
    if (plainText) {
        const key = await getOrCreateCryptoKey();
        payloadContent = await encryptMessage(plainText, key);
    }

    const payload = {
        type: "message",
        sender: currentUserPhone,
        receiver: selectedUser,
        group_id: selectedGroupId,
        msg_type: msgType,
        content: payloadContent,
        file_url: fileUrl,
        reply_to_id: replyMessageId
    };

    socket.send(JSON.stringify(payload));

    if (input) input.value = "";
    replyMessageId = null;
}

// 🟢 5. UI Rendering Engine
function appendMessageToUI(msg) {
    const chatBox = document.getElementById("chatBox");
    if (!chatBox) return;

    // Prevent duplicate entries
    if (msg.id && document.getElementById(`msg-${msg.id}`)) return;

    const isOutgoing = String(msg.sender) === String(currentUserPhone);
    const msgDiv = document.createElement("div");
    msgDiv.id = msg.id ? `msg-${msg.id}` : `msg-temp-${Date.now()}`;
    
    msgDiv.className = `message-bubble ${isOutgoing ? "outgoing" : "incoming"}`;
    if (isOutgoing) {
        msgDiv.style.marginLeft = "auto";
        msgDiv.style.marginRight = "0";
        msgDiv.style.backgroundColor = "#005c4b";
        msgDiv.style.color = "#ffffff";
    } else {
        msgDiv.style.marginLeft = "0";
        msgDiv.style.marginRight = "auto";
        msgDiv.style.backgroundColor = "#202c33";
        msgDiv.style.color = "#ffffff";
    }

    let tickHtml = "";
    if (isOutgoing) {
        let isRead = msg.status === "read";
        let color = isRead ? "#53bdeb" : "#8696a0";
        let iconClass = msg.status === "sent" ? "fa-check" : "fa-check-double";
        tickHtml = `<span id="tick-${msg.id || ''}" class="msg-tick" style="margin-left:5px;"><i class="fa-solid ${iconClass}" style="color:${color};"></i></span>`;
    }

    let bodyContent = `<div class="msg-text">${msg.content || ''}</div>`;
    if (msg.msg_type === "image") {
        bodyContent = `<img src="${msg.file_url}" class="chat-img" style="max-width:200px; border-radius:8px;" /><div class="msg-text">${msg.content || ''}</div>`;
    } else if (msg.msg_type === "voice") {
        bodyContent = `<audio controls src="${msg.file_url}"></audio>`;
    } else if (msg.msg_type === "document") {
        bodyContent = `<a href="${msg.file_url}" target="_blank" style="color:#53bdeb;">📄 Download Document</a>`;
    }

    msgDiv.innerHTML = `
        ${msg.reply_to_id ? `<div class="quoted-reply" style="font-size:0.8em; opacity:0.7;">Replying to #${msg.reply_to_id}</div>` : ''}
        ${bodyContent}
        <div class="msg-meta" style="font-size:0.7em; text-align:right; opacity:0.7; margin-top:2px;">
            <span class="msg-time">${msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            ${tickHtml}
        </div>
    `;

    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function updateUnreadBadgeUI(phone) {
    const contactElem = document.querySelector(`[data-phone="${phone}"] .contact-bottom`);
    if (contactElem) {
        let badge = contactElem.querySelector(".unread-badge");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "unread-badge";
            badge.style.cssText = "background:#00a884; color:#fff; border-radius:50%; padding:2px 6px; font-size:12px; float:right;";
            contactElem.appendChild(badge);
        }
        badge.innerText = unreadCounts[phone] > 0 ? unreadCounts[phone] : "";
    }
}

// 🟢 6. Chat & Contact Interactions
async function loadChatHistory(contactPhone) {
    const chatBox = document.getElementById("chatBox");
    if (!chatBox) return;
    chatBox.innerHTML = "";

    try {
        const res = await fetch(`/messages/${currentUserPhone}/${contactPhone}`);
        const messages = await res.json();
        
        if (Array.isArray(messages)) {
            for (let msg of messages) {
                if (msg.content) {
                    msg.content = await decryptMessage(msg.content, sharedCryptoKey);
                }
                appendMessageToUI(msg);
            }
        }
    } catch (err) {
        console.error("Error loading chat history:", err);
    }
}

function selectContact(phone, name) {
    selectedUser = phone;
    selectedGroupId = null;

    // Reset unread counts
    unreadCounts[phone] = 0;
    updateUnreadBadgeUI(phone);

    const emptyState = document.getElementById("emptyState");
    const activeChatWrapper = document.getElementById("activeChatWrapper");

    if (emptyState) emptyState.style.display = "none";
    if (activeChatWrapper) activeChatWrapper.style.display = "flex";

    document.getElementById("chatWithTitle").innerText = name;
    document.getElementById("chatStatusText").innerText = "Online";

    const activeAvatar = document.getElementById("activeAvatar");
    if (activeAvatar) {
        activeAvatar.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=00a884&color=fff`;
    }

    loadChatHistory(phone);
}

async function loadContactsAndGroups() {
    try {
        const res = await fetch(`/contacts/${currentUserPhone}`);
        const contacts = await res.json();
        const list = document.getElementById("userList");
        if (!list) return;
        list.innerHTML = "";

        if (!contacts || contacts.length === 0) {
            list.innerHTML = '<li style="padding:15px; color:#8696a0; text-align:center;">No contacts yet. Click + icon to add.</li>';
            return;
        }

        contacts.forEach(c => {
            const li = document.createElement("li");
            li.className = "contact-item";
            li.setAttribute("data-phone", c.phone);
            li.setAttribute("data-name", c.name.toLowerCase());
            li.innerHTML = `
                <div class="contact-avatar"><img src="https://ui-avatars.com/api/?name=${encodeURIComponent(c.name)}&background=00a884&color=fff"></div>
                <div class="contact-info" style="width:100%;">
                    <div class="contact-top"><span>${c.name}</span></div>
                    <div class="contact-bottom"><span>${c.phone}</span></div>
                </div>
            `;
            li.onclick = () => selectContact(c.phone, c.name);
            list.appendChild(li);
        });
    } catch (err) {
        console.error("Load contacts error:", err);
    }
}

async function promptAddContact() {
    const phone = prompt("Enter the Phone Number to add:");
    if (!phone) return;

    if (phone.trim() === currentUserPhone) {
        return alert("You cannot add your own phone number!");
    }

    try {
        const res = await fetch("/contacts/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_phone: currentUserPhone, contact_phone: phone.trim() })
        });

        const result = await res.json();
        if (result.success) {
            alert("Contact added!");
            loadContactsAndGroups();
        } else {
            alert(result.message || "User not found!");
        }
    } catch (err) {
        alert("Error adding contact!");
    }
}

// 🟢 7. Audio Recording Features
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
        alert("Microphone permission required!");
    }
}

function stopVoiceRecording() {
    if (mediaRecorder) mediaRecorder.stop();
}

function reactToMessage(msgId, emoji) {
    if (!socket) return;
    socket.send(JSON.stringify({
        type: "reaction",
        message_id: msgId,
        emoji: emoji,
        receiver: selectedUser
    }));
}

// 🟢 8. View Navigation & Utilities
function closeChatMobile() {
    const activeChatWrapper = document.getElementById("activeChatWrapper");
    const emptyState = document.getElementById("emptyState");

    if (activeChatWrapper) activeChatWrapper.style.display = "none";
    if (emptyState) emptyState.style.display = "flex";
}

function setupSearchFilter() {
    const searchInput = document.getElementById("contactSearch");
    if (!searchInput) return;

    searchInput.addEventListener("input", function (e) {
        const query = e.target.value.toLowerCase();
        const items = document.querySelectorAll("#userList .contact-item");

        items.forEach(item => {
            const name = item.getAttribute("data-name") || "";
            if (name.includes(query)) {
                item.style.display = "flex";
            } else {
                item.style.display = "none";
            }
        });
    });
}

function openProfileDrawer() {
    alert(`Logged in User: ${currentUserPhone}`);
}
