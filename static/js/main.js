let currentUserPhone = "";
let selectedUser = "";
let socket = null;

// Send OTP Simulation (Replace with Firebase API in production)
function sendOTP() {
    const phone = document.getElementById("userPhone").value.trim();
    if (!phone || phone.length < 10) return alert("Please enter a valid phone number!");
    
    currentUserPhone = phone;
    document.getElementById("phoneStep").style.display = "none";
    document.getElementById("otpStep").style.display = "block";
    alert("OTP sent! (Use default OTP: 123456)");
}

// Verify OTP & Login
function verifyOTP() {
    const otp = document.getElementById("otpCode").value.trim();
    if (otp !== "123456") return alert("Invalid OTP code!");

    document.getElementById("loginScreen").style.display = "none";
    document.getElementById("appContainer").style.display = "flex";
    
    connectWebSocket();
    loadContacts();
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/${currentUserPhone}`);
    
    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === "message" && (data.sender === selectedUser || data.sender === currentUserPhone)) {
            appendMessage(data.sender, data.message, data.file_url, data.timestamp);
        }
    };
}

// Fetch Contacts from Database
async function loadContacts() {
    try {
        const res = await fetch(`/contacts/${currentUserPhone}`);
        const contacts = await res.json();
        const list = document.getElementById("userList");
        list.innerHTML = "";

        contacts.forEach(c => {
            const li = document.createElement("li");
            li.className = "contact-item";
            li.innerHTML = `
                <div class="contact-avatar"><img src="https://ui-avatars.com/api/?name=${c.name}"></div>
                <div class="contact-info">
                    <div class="contact-top"><span>${c.name}</span></div>
                    <div class="contact-bottom"><span>${c.phone}</span></div>
                </div>
            `;
            li.onclick = () => selectContact(c.phone, c.name);
            list.appendChild(li);
        });
    } catch (err) { console.error(err); }
}

// Add New Contact Dynamic Check
async function promptAddContact() {
    const phone = prompt("Enter User Phone Number:");
    if (!phone) return;

    const res = await fetch("/contacts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_phone: currentUserPhone, contact_phone: phone })
    });
    
    const result = await res.json();
    if (result.success) {
        alert("Contact added!");
        loadContacts();
    } else {
        alert(result.message || "User not registered on Qtalk!");
    }
}
