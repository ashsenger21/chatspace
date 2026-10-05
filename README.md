# ChatSpace 💬

A full-stack real-time chat application built with **Python Flask**, **SQLite**, **WebSockets**, and vanilla **HTML/CSS/JavaScript**.

---

## Features

- 🔐 User registration & login with hashed passwords
- 💬 Real-time messaging via WebSockets (Flask-SocketIO)
- 📷 Photo sharing (JPG, PNG, GIF, WEBP)
- 🎬 Video sharing (MP4, WEBM, MOV)
- 🎙️ Voice messages (recorded in-browser via MediaRecorder API)
- 🔍 Search users, conversations, and messages
- 👤 Profile settings (username, password, profile picture)
- 🌙 Dark / Light mode toggle
- 📱 Fully responsive (mobile, tablet, desktop)
- ✅ Typing indicators, online/offline status, read receipts

---

## Requirements

- Python 3.8 or higher
- pip (Python package manager)
- A modern web browser (Chrome, Firefox, Edge)

---

## Installation

### 1. Navigate to the project folder

```
cd chatspace
```

### 2. Create a virtual environment

A virtual environment keeps your project's packages separate from your system Python:

```
python -m venv venv
```

### 3. Activate the virtual environment

**Windows:**
```
venv\Scripts\activate
```

**Mac/Linux:**
```
source venv/bin/activate
```

You should see `(venv)` at the start of your command prompt.

### 4. Install dependencies

```
pip install -r requirements.txt
```

This installs:
- **Flask** – the web framework
- **Flask-SocketIO** – real-time WebSocket support
- **Flask-Login** – user session management
- **Flask-SQLAlchemy** – database ORM
- **Werkzeug** – password hashing and security utilities

---

## Database Setup

The database is created automatically when you first run the app. No manual setup needed.

SQLite stores everything in a single file: `database.db`

---

## Running the Application

```
python app.py
```

Then open your browser and go to:

```
http://localhost:5000
```

Press **Ctrl+C** in the terminal to stop the server.

---

## Project Structure

```
chatspace/
│
├── app.py              # Main entry point – Flask app + WebSocket events
├── config.py           # All configuration settings
├── requirements.txt    # Python dependencies
├── database.db         # SQLite database (auto-created on first run)
│
├── models/             # Database table definitions
│   ├── __init__.py     # Creates the `db` object shared by all models
│   ├── user.py         # User table (id, username, password_hash, etc.)
│   ├── conversation.py # Conversation table (pairs of users)
│   └── message.py      # Message table (text, image, video, audio)
│
├── routes/             # URL route handlers (Blueprint groups)
│   ├── __init__.py
│   ├── auth.py         # /register, /login, /logout
│   ├── chat.py         # /home, /api/conversations, /api/messages, etc.
│   └── profile.py      # /profile, /profile/username, /profile/password
│
├── templates/          # HTML pages (Jinja2 templates)
│   ├── login.html
│   ├── register.html
│   ├── home.html       # Main chat dashboard
│   └── profile.html
│
├── static/             # Frontend assets
│   ├── css/
│   │   ├── style.css   # Main app styles (dark/light mode, responsive)
│   │   └── auth.css    # Login/register page styles
│   └── js/
│       ├── app.js      # Core: theme, conversations, search, avatars
│       ├── chat.js     # Chat: WebSocket, messages, media sending
│       └── audio.js    # Voice recording: MediaRecorder API
│
└── uploads/            # Uploaded media files (auto-created)
    ├── images/
    ├── videos/
    └── audio/
```

---

## How the Major Python Files Work

### `app.py`
The heart of the application. It:
1. Creates the Flask app and loads config
2. Initialises SQLAlchemy (database), Flask-Login (sessions), and Flask-SocketIO (WebSockets)
3. Registers the three route Blueprints
4. Creates database tables on startup
5. Defines all WebSocket event handlers (connect, disconnect, send_message, typing, etc.)
6. Runs the development server

### `config.py`
All settings in one place: secret key, database path, upload limits, allowed file extensions.

### `models/user.py`
Defines the `users` database table. Uses `UserMixin` from Flask-Login to integrate with the session system. Passwords are **never stored in plain text** – only a bcrypt hash.

### `models/conversation.py`
Defines the `conversations` table. Each row represents a chat between two users. Uses a smart trick: always stores the lower user ID as `user1_id` so there can never be two rows for the same pair of users.

### `models/message.py`
Defines the `messages` table. Each message has a `message_type` (`text`, `image`, `video`, `audio`) which tells the frontend how to display it.

### `routes/auth.py`
Handles user registration, login, and logout. Uses `werkzeug.security.generate_password_hash` and `check_password_hash` for secure password handling.

### `routes/chat.py`
All the chat API endpoints. Returns JSON so the JavaScript frontend can fetch and display data without page reloads.

### `routes/profile.py`
Lets users update their username, password, and profile picture.

---

## How WebSockets Work

Normal HTTP works like a walkie-talkie: you press a button (request), get a response, and that's it. The connection closes.

**WebSockets** are like an open phone call: once connected, both sides can send messages to each other at any time.

In ChatSpace:
1. When you open the app, the browser connects to the Flask-SocketIO server
2. When you open a conversation, your browser "joins" that conversation's room
3. When you send a message, the server saves it and immediately broadcasts it to everyone in that room
4. The other person's browser receives the message and displays it instantly — no page refresh needed

Key events used:
- `send_message` – browser sends a text message
- `new_message` – server pushes a new message to the conversation room
- `typing` / `typing_indicator` – typing notifications
- `user_status` – online/offline changes
- `media_sent` – notifies after a media file is uploaded via HTTP

---

## How Media Uploads Work

Media (photos, videos, voice) is uploaded via a regular HTTP POST request (not WebSocket, because WebSockets aren't designed for large binary data).

Flow:
1. User selects/records a file
2. JavaScript sends a `FormData` POST to `/api/conversation/<id>/send_media`
3. Flask validates the file type and size, saves it with a UUID filename
4. A `Message` row is created in the database with the file path
5. The JavaScript then emits a `media_sent` WebSocket event with the new message ID
6. Flask-SocketIO broadcasts the message to the conversation room
7. The other user's browser displays it

Files are stored in `uploads/images/`, `uploads/videos/`, and `uploads/audio/`.

---

## How Voice Recording Works

Voice messages use the browser's **MediaRecorder API**:

1. User clicks the microphone button
2. The browser asks for microphone permission
3. If granted, `MediaRecorder` starts capturing audio from the microphone
4. Audio data arrives in chunks every 250ms and is stored in an array
5. When the user clicks "Send", recording stops
6. All chunks are combined into a single audio `Blob` (binary file)
7. The Blob is uploaded as a form file to the server
8. The server saves it and creates a `Message` with `message_type="audio"`
9. The other user receives an audio player in their chat

If microphone permission is denied, a friendly error message is shown.

---

## Security Notes

- Passwords are hashed with PBKDF2-SHA256 (via Werkzeug) — never stored in plain text
- Uploaded files get UUID-based random names to prevent collisions
- File extensions are strictly validated; only allowed types are accepted
- `send_from_directory` is used to serve uploads, which prevents path traversal attacks
- All chat/media routes require login; unauthenticated users are redirected
- File size is capped at 100MB

---

## Troubleshooting

**"Module not found" error:**
Make sure your virtual environment is activated (`venv\Scripts\activate`) and dependencies are installed (`pip install -r requirements.txt`).

**Port 5000 already in use:**
Another program is using port 5000. Either close it, or change the port in `app.py`:
```python
socketio.run(app, host="0.0.0.0", port=5001, ...)
```

**Database errors:**
Delete `database.db` and restart the app — it will be recreated fresh.

**Voice recording not working:**
The browser requires HTTPS or localhost for microphone access. Make sure you're visiting `http://localhost:5000` (not a local IP like `192.168.x.x`).

---

## Running the Automated Tests

To run the unit and integration test suite:

```bash
# Run unit & integration tests
python -m unittest discover -s tests -v

# Run the live server end-to-end integration test (with server running)
python tests/test_live_server.py
```

