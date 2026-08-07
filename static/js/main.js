let currentUserPhone = "";
let selectedUser = "";
let selectedUserName = "";
let socket = null;

// 🟢 1. Send OTP Simulation
function sendOTP() {
    const phone = document.getElementById("userPhone").value.trim();
    if (!phone || phone.length < 10) {
        return alert("Please enter a valid phone number!");
    }
    
    currentUserPhone = phone;
    document.getElementById("phoneStep").style.display = "none";
    document.getElementById("otpStep").style.display = "block";
    alert("OTP sent! (Use default OTP: 123456)");
}

// 🟢 2. Verify OTP & Register User automatically in Database
async function verifyOTP() {
    const otp = document.getElementById("otpCode").value.trim();
    if (otp !== "123456") {
        return alert("Invalid OTP code!");
    }

    try {
        // Register user in Backend DB upon verification
        await fetch("/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                phone: currentUserPhone, 
                name: "User " + currentUserPhone.slice(-4) 
            })
        });
    } catch (err) {
        console.error("Registration error:", err);
    }

    // Show Main App Screen
    document.getElementById("loginScreen").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    
    connectWebSocket();
    loadContacts();
}

// 🟢 3. Connect WebSocket for Real-time Messaging
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUserPhone}`);
    
    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === "message" && (data.sender === selectedUser || data.sender === currentUserPhone)) {
            appendMessage(data.sender, data.message, data.file_url, data.timestamp);
        }
    };

    socket.onclose = function() {
        console.log("WebSocket disconnected. Retrying...");
        setTimeout(connectWebSocket, 3000);
    };
}

// 🟢 4. Fetch Contact List
async function loadContacts() {
    try {
        const res = await fetch(`/contacts/${currentUserPhone}`);
        const contacts = await res.json();
        const list = document.getElementById("userList");
        list.innerHTML = "";

        if (!contacts || contacts.length === 0) {
            list.innerHTML = '<li style="padding:15px; color:#8696a0; text-align:center;">No contacts yet. Click + to add.</li>';
            return;
        }

        contacts.forEach(c => {
            const li = document.createElement("li");
            li.className = `contact-item ${c.phone === selectedUser ? 'active' : ''}`;
            li.innerHTML = `
                <div class="contact-avatar"><img src="https://ui-avatars.com/api/?name=${encodeURIComponent(c.name)}&background=00a884&color=fff"></div>
                <div class="contact-info">
                    <div class="contact-top"><span>${c.name}</span></div>
                    <div class="contact-bottom"><span>${c.phone}</span></div>
                </div>
            `;
            li.onclick = () => selectContact(c.phone, c.name);
            list.appendChild(li);
        });
    } catch (err) { 
        console.error("Error loading contacts:", err); 
    }
}

// 🟢 5. Select Contact to Chat
function selectContact(phone, name) {
    selectedUser = phone;
    selectedUserName = name;

    const emptyState = document.getElementById("emptyState");
    const activeChatWrapper = document.getElementById("activeChatWrapper");
    
    if (emptyState) emptyState.style.display = "none";
    if (activeChatWrapper) activeChatWrapper.style.display = "flex";

    document.getElementById("chatWithTitle").innerText = name;
    document.getElementById("chatStatusText").innerText = phone;
    document.getElementById("activeAvatar").src = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=00a884&color=fff`;

    const chatBox = document.getElementById("chatBox");
    if (chatBox) chatBox.innerHTML = "";

    loadContacts(); 
}

// 🟢 6. Add Contact Dynamically
async function promptAddContact() {
    const phone = prompt("Enter User Phone Number:");
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
            alert("Contact added successfully!");
            loadContacts();
        } else {
            alert(result.message || "User not registered on Qtalk!");
        }
    } catch (err) {
        console.error("Error adding contact:", err);
        alert("Error connecting to server!");
    }
}

// 🟢 7. Send Message
function sendMessage() {
    const input = document.getElementById("messageInput");
    const message = input.value.trim();

    if (!message || !selectedUser || !socket) return;

    const payload = {
        type: "message",
        receiver: selectedUser,
        message: message
    };

    socket.send(JSON.stringify(payload));
    appendMessage(currentUserPhone, message, null, new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    input.value = "";
}

// 🟢 8. Append Message to Chat Window
function appendMessage(sender, message, file_url = null, timestamp = "") {
    const chatBox = document.getElementById("chatBox");
    if (!chatBox) return;

    const isOutgoing = sender === currentUserPhone;
    const msgDiv = document.createElement("div");
    msgDiv.className = `message-bubble ${isOutgoing ? "outgoing" : "incoming"}`;

    let content = `<div class="message-text">${message}</div>`;
    if (file_url) {
        content += `<div class="message-file"><a href="${file_url}" target="_blank">View Attachment</a></div>`;
    }
    content += `<div class="message-time">${timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>`;

    msgDiv.innerHTML = content;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// 🟢 9. Handle Enter Key Press
function handleKeyPress(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
}

// 🟢 10. Mobile Navigation (Back Button)
function closeChatMobile() {
    const activeChatWrapper = document.getElementById("activeChatWrapper");
    if (activeChatWrapper) activeChatWrapper.style.display = "none";
    selectedUser = "";
}
