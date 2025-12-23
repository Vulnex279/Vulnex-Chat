const socket = io();
let partner = null;
const me = document.body.dataset.user;
let typingTimeout;

// 1. Load Users & Handle Search
function loadUsers() {
    fetch('/get_users').then(r => r.json()).then(users => {
        const term = document.getElementById('user-search').value.toLowerCase();
        const filtered = users.filter(u => u.username.toLowerCase().includes(term));
        
        document.getElementById('user-list').innerHTML = filtered.map(u => `
            <div class="user-item" onclick="startChat('${u.username}')">
                <div class="avatar">${u.username[0].toUpperCase()}</div>
                <div style="flex:1;">
                    <div style="font-weight:bold;">${u.username} ${u.username === 'Daniel' ? '⭐' : ''}</div>
                    <div style="font-size:0.75rem; color:#708499;">${u.online ? 'Online' : 'Offline'}</div>
                </div>
                <span class="dot ${u.online ? 'on' : ''}"></span>
            </div>
        `).join('');
    });
}

function searchUsers() { loadUsers(); }

// 2. Start Chat (Mobile Compatible)
function startChat(u) {
    partner = u;
    document.getElementById('active-user').innerText = u;
    document.getElementById('message-area').innerHTML = "";
    document.body.classList.add('mobile-active'); // Triggers CSS slide
    
    socket.emit('join_private', {username: me, partner: u});
    fetch(`/get_history/${u}`).then(r => r.json()).then(data => data.forEach(renderMsg));
}

function closeChat() {
    document.body.classList.remove('mobile-active'); // Slides back to list
    partner = null;
}

// 3. Send Message Logic (Button + Enter Key)
function sendMessage() {
    const i = document.getElementById('msg-in');
    if(i.value.trim() && partner) {
        socket.emit('private_message', {msg: i.value, sender: me, recipient: partner, type: 'text'});
        i.value = "";
    }
}

document.getElementById('send-btn').onclick = sendMessage;

document.getElementById('msg-in').addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        event.preventDefault(); // Stop line break
        sendMessage();
    } else {
        // Typing indicator
        if(partner) socket.emit('typing', {sender: me, recipient: partner});
    }
});

// 4. Render Message
function renderMsg(d) {
    const area = document.getElementById('message-area');
    const div = document.createElement('div');
    const isMe = d.sender === me;
    div.className = `bubble ${isMe ? 'sent' : 'received'}`;
    
    let content = d.message || d.msg;
    if(['jpg','png','jpeg','gif'].includes(d.type)) {
        content = `<img src="${content}" style="max-width:100%; border-radius:10px;">`;
    }
    
    const time = new Date(d.timestamp * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    const tickColor = d.seen === 1 ? 'color:#3390ec;' : 'color:#708499;';
    
    div.innerHTML = `${content} <span class="ts">${time} <span style="${tickColor}">${isMe ? '✔️✔️' : ''}</span></span>`;
    
    area.appendChild(div);
    area.scrollTop = area.scrollHeight; // Auto-scroll
    
    // Alert Sound
    if(!isMe) {
        document.getElementById('ping-sound').play().catch(e => console.log("Audio play blocked by browser"));
    }
}

// 5. Socket Listeners
socket.on('new_message', renderMsg);
socket.on('status_change', () => loadUsers());

socket.on('is_typing', d => {
    if(d.sender === partner) {
        const el = document.getElementById('typing-status');
        el.innerText = "typing...";
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => el.innerText = "", 2000);
    }
});

// File Upload
function uploadFile() {
    const input = document.getElementById('file-up');
    if (!input.files[0]) return;
    let formData = new FormData();
    formData.append('file', input.files[0]);
    fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => socket.emit('private_message', { msg: data.url, sender: me, recipient: partner, type: data.type }));
}

loadUsers();