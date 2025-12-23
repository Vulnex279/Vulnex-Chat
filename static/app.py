from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, os, time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vulnex_final_production_2025'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Create upload folder if missing
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

socketio = SocketIO(app, cors_allowed_origins="*")
online_users = set()

def get_db():
    conn = sqlite3.connect('chat_history.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        # Create Users Table
        db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)')
        # Create Messages Table with 'seen' and 'type'
        db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, recipient TEXT, message TEXT, type TEXT, timestamp REAL, seen INTEGER DEFAULT 0)')
        db.commit()
        db.close()

# Initialize DB on start
init_db()

@app.route('/')
def index():
    if 'username' in session: return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username'].strip()
        user = get_db().execute('SELECT * FROM users WHERE username = ?', (u,)).fetchone()
        if user and check_password_hash(user['password'], request.form['password']):
            session['username'] = u
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        h = generate_password_hash(request.form['password'])
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (request.form['username'].strip(), h))
            db.commit()
            return redirect(url_for('login'))
        except: return "Identity Taken"
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/get_users')
def get_users():
    if 'username' not in session: return jsonify([])
    users = get_db().execute('SELECT username FROM users WHERE username != ?', (session['username'],)).fetchall()
    return jsonify([{'username': u['username'], 'online': u['username'] in online_users} for u in users])

@app.route('/get_history/<partner>')
def get_history(partner):
    db = get_db()
    # Mark messages as seen (Blue Ticks)
    db.execute('UPDATE messages SET seen = 1 WHERE sender = ? AND recipient = ?', (partner, session['username']))
    db.commit()
    msgs = db.execute('SELECT * FROM messages WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?) ORDER BY timestamp ASC', (session['username'], partner, partner, session['username'])).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({'error': 'no file'})
    f = request.files['file']
    if f.filename == '': return jsonify({'error': 'no filename'})
    fn = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{fn}")
    f.save(path)
    # Return path relative to static
    return jsonify({'url': f"/{path}", 'type': fn.rsplit('.', 1)[1].lower()})

@socketio.on('connect')
def connect():
    if 'username' in session:
        online_users.add(session['username'])
        emit('status_change', {'user': session['username'], 'status': 'online'}, broadcast=True)

@socketio.on('disconnect')
def disconnect():
    if 'username' in session:
        online_users.discard(session['username'])
        emit('status_change', {'user': session['username'], 'status': 'offline'}, broadcast=True)

@socketio.on('join_private')
def join(data):
    room = "_".join(sorted([data['username'], data['partner']]))
    join_room(room)

@socketio.on('private_message')
def msg(data):
    room = "_".join(sorted([data['sender'], data['recipient']]))
    db = get_db()
    db.execute('INSERT INTO messages (sender, recipient, message, type, timestamp) VALUES (?,?,?,?,?)', 
               (data['sender'], data['recipient'], data['msg'], data.get('type','text'), time.time()))
    db.commit()
    data['timestamp'] = time.time()
    emit('new_message', data, room=room)

@socketio.on('typing')
def typing(data):
    room = "_".join(sorted([data['sender'], data['recipient']]))
    emit('is_typing', data, room=room)

if __name__ == '__main__':
    socketio.run(app, debug=True)