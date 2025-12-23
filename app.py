import sqlite3
import os
import html
import time
from datetime import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, send, emit
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vulnex_secret_key_123'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- MEMORY ---
connected_users = {} 
failed_attempts = {} # 🛡️ FIREWALL MEMORY: { 'IP_ADDRESS': {'count': 0, 'ban_until': 0} }

# --- KEYS ---
if os.path.exists("secret.key"):
    with open("secret.key", "rb") as key_file:
        key = key_file.read()
else:
    key = Fernet.generate_key()
    with open("secret.key", "wb") as key_file:
        key_file.write(key)
cipher_suite = Fernet(key)

# --- DB INIT ---
def init_db():
    conn = sqlite3.connect('chat_history.db')
    curr = conn.cursor()
    curr.execute('''CREATE TABLE IF NOT EXISTS Messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, content TEXT, timestamp TEXT)''')
    curr.execute('''CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password_hash TEXT)''')
    conn.commit()
    conn.close()
init_db()

@app.route('/')
def index():
    return render_template('index.html')

# --- EVENTS ---

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    user = connected_users.get(request.sid)
    if user:
        del connected_users[request.sid]
        print(f"❌ {user} disconnected.")
        emit('message', {'user': 'SYSTEM', 'msg': f'{user} has left the channel.', 'time': ''}, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('display_typing', {'user': data['user']}, broadcast=True, include_self=False)

@socketio.on('login')
def handle_login(data):
    # 🛡️ 1. GET USER IP (Simulated for Localhost)
    # In real cloud, we would use request.remote_addr or headers
    user_ip = request.remote_addr 
    
    # 🛡️ 2. CHECK FIREWALL
    current_time = time.time()
    if user_ip in failed_attempts:
        record = failed_attempts[user_ip]
        # Is user currently banned?
        if record['ban_until'] > current_time:
            wait_time = int(record['ban_until'] - current_time)
            emit('login_response', {'status': 'fail', 'msg': f'⛔ SYSTEM LOCKDOWN. Try again in {wait_time}s.'})
            return

    username = data['user']
    password = data['pass']
    
    conn = sqlite3.connect('chat_history.db')
    curr = conn.cursor()
    curr.execute("SELECT password_hash FROM Users WHERE username=?", (username,))
    row = curr.fetchone()
    conn.close()
    
    if row and check_password_hash(row[0], password):
        # ✅ SUCCESS: Reset attempts
        if user_ip in failed_attempts:
            del failed_attempts[user_ip]
            
        connected_users[request.sid] = username
        emit('login_response', {'status': 'success'})
        emit('message', {'user': 'SYSTEM', 'msg': f'{username} has joined.', 'time': ''}, broadcast=True)
        
        # Load History
        conn = sqlite3.connect('chat_history.db')
        curr = conn.cursor()
        curr.execute("SELECT username, content, timestamp FROM Messages ORDER BY id ASC")
        rows = curr.fetchall()
        for r in rows:
            try:
                decrypted = cipher_suite.decrypt(r[1].encode('utf-8')).decode('utf-8')
                emit('message', {'user': r[0], 'msg': decrypted, 'time': r[2]})
            except: pass
    else:
        # ❌ FAIL: Increment Counter
        if user_ip not in failed_attempts:
            failed_attempts[user_ip] = {'count': 0, 'ban_until': 0}
        
        failed_attempts[user_ip]['count'] += 1
        
        # 🛡️ 3. BAN IF 3 FAILS
        if failed_attempts[user_ip]['count'] >= 3:
            failed_attempts[user_ip]['ban_until'] = current_time + 30 # Ban for 30 seconds
            emit('login_response', {'status': 'fail', 'msg': '⛔ TOO MANY ATTEMPTS. IP BANNED FOR 30s.'})
        else:
            remaining = 3 - failed_attempts[user_ip]['count']
            emit('login_response', {'status': 'fail', 'msg': f'Invalid Password! {remaining} attempts left.'})

@socketio.on('register')
def handle_register(data):
    username = html.escape(data['user'])
    password = data['pass']
    hashed_pw = generate_password_hash(password)
    try:
        conn = sqlite3.connect('chat_history.db')
        curr = conn.cursor()
        curr.execute("INSERT INTO Users (username, password_hash) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        conn.close()
        emit('register_response', {'status': 'success', 'msg': 'Registration Successful!'})
    except:
        emit('register_response', {'status': 'fail', 'msg': 'Username taken!'})

@socketio.on('message')
def handle_message(data):
    username = data['user']
    clean_msg = html.escape(data['msg']) # 🛡️ Sanitize
    current_time = datetime.now().strftime("%I:%M %p") 

    msg_bytes = clean_msg.encode('utf-8')
    encrypted_msg = cipher_suite.encrypt(msg_bytes).decode('utf-8')
    
    conn = sqlite3.connect('chat_history.db')
    curr = conn.cursor()
    curr.execute("INSERT INTO Messages (username, content, timestamp) VALUES (?, ?, ?)", (username, encrypted_msg, current_time))
    conn.commit()
    conn.close()

    decrypted_content = cipher_suite.decrypt(encrypted_msg.encode('utf-8')).decode('utf-8')
    send({"user": username, "msg": decrypted_content, "time": current_time}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)