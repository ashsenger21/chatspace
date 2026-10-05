"""
app.py - ChatSpace Main Application Entry Point

This is the central file that:
  1. Creates the Flask application
  2. Configures it from config.py
  3. Initialises extensions (SQLAlchemy, Flask-Login, Flask-SocketIO)
  4. Registers Blueprints (route groups)
  5. Creates database tables
  6. Defines WebSocket (SocketIO) event handlers
  7. Runs the development server

Think of this file as the "glue" that connects all the other pieces together.
"""

import os
from datetime import datetime, timezone

# Load environment variables from .env file (ignored in production where env vars are set directly)
from dotenv import load_dotenv
load_dotenv()

# Eventlet monkey-patching MUST happen before any other imports for WebSocket
# support in production. This makes standard Python I/O non-blocking.
import eventlet
eventlet.monkey_patch()

from flask import Flask, request
from flask_login import LoginManager, current_user, login_required
from flask_socketio import SocketIO, emit, join_room, leave_room

from config import Config
from models import db
from models.user import User
from models.conversation import Conversation
from models.message import Message

# ---------------------------------------------------------------------------
# 1. Create Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)  # Load all settings from config.py

# ---------------------------------------------------------------------------
# 2. Initialise Extensions
# ---------------------------------------------------------------------------
db.init_app(app)      # Connect SQLAlchemy to our app

# Flask-Login manages user sessions (who is logged in)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view  = "auth.login"   # Where to redirect unauthenticated users
login_manager.login_message = "Please log in to access ChatSpace."
login_manager.login_message_category = "info"

# Flask-SocketIO enables real-time bidirectional communication via WebSockets
# async_mode="threading" works well for development without needing eventlet
socketio = SocketIO(
    app,
    cors_allowed_origins="*",           # Allow connections from the same host
    async_mode=Config.SOCKETIO_ASYNC_MODE
)

# ---------------------------------------------------------------------------
# 3. Flask-Login: tell it how to load a user from a session cookie
# ---------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login calls this function with the user ID stored in the session.
    We return the User object (or None if not found).
    """
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# 4. Register Blueprints (route groups)
# ---------------------------------------------------------------------------
from routes.auth    import auth_bp
from routes.chat    import chat_bp
from routes.profile import profile_bp

app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(profile_bp)


# ---------------------------------------------------------------------------
# 5. Create database tables (runs once when the app starts)
# ---------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    print("[OK] Database tables created/verified.")


# ---------------------------------------------------------------------------
# 6. WebSocket Event Handlers
#
# WebSockets are a persistent connection between the browser and the server.
# Unlike regular HTTP (request→response), WebSockets stay open so the server
# can PUSH data to the browser at any time without the browser asking.
#
# How it works:
#   Browser connects → server gets "connect" event
#   Browser sends event → server handles it, can emit back to anyone
#   Browser disconnects → server gets "disconnect" event
# ---------------------------------------------------------------------------

# We use "rooms" to deliver messages only to the right conversation.
# Each conversation gets a room named "conv_<id>".
# Each user also has a personal room named "user_<id>" for notifications.

@socketio.on("connect")
def handle_connect():
    """Called when a client (browser tab) connects via WebSocket."""
    if current_user.is_authenticated:
        # Mark user as online in the database
        current_user.is_online = True
        current_user.update_last_seen()
        db.session.commit()

        # Put this socket in the user's personal room
        join_room(f"user_{current_user.id}")

        # Tell everyone who cares that this user is online
        emit("user_status", {
            "user_id": current_user.id,
            "is_online": True,
            "username": current_user.username,
        }, broadcast=True)

        print(f"[CONNECT] {current_user.username} connected.")


@socketio.on("disconnect")
def handle_disconnect():
    """Called when a client disconnects (browser tab closed, navigated away, etc.)."""
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()

        emit("user_status", {
            "user_id": current_user.id,
            "is_online": False,
            "last_seen": current_user.last_seen.isoformat(),
            "username": current_user.username,
        }, broadcast=True)

        print(f"[DISCONNECT] {current_user.username} disconnected.")


@socketio.on("join_conversation")
def handle_join_conversation(data):
    """
    Browser emits this when the user opens a conversation.
    We put the socket in the conversation's room so it receives new messages.
    """
    conv_id = data.get("conversation_id")
    if not conv_id or not current_user.is_authenticated:
        return

    conv = db.session.get(Conversation, conv_id)
    if conv and current_user.id in [conv.user1_id, conv.user2_id]:
        join_room(f"conv_{conv_id}")
        emit("joined_conversation", {"conversation_id": conv_id})


@socketio.on("leave_conversation")
def handle_leave_conversation(data):
    """Browser emits this when the user closes a conversation."""
    conv_id = data.get("conversation_id")
    if conv_id:
        leave_room(f"conv_{conv_id}")


@socketio.on("send_message")
def handle_send_message(data):
    """
    Browser emits this when the user sends a text message.
    We save it to the database, then broadcast it to the conversation room
    so the recipient (if connected) sees it instantly.
    """
    if not current_user.is_authenticated:
        return

    conv_id = data.get("conversation_id")
    text    = (data.get("text") or "").strip()

    if not conv_id or not text:
        return

    if len(text) > 5000:
        emit("error", {"message": "Message too long."})
        return

    conv = db.session.get(Conversation, conv_id)
    if not conv or current_user.id not in [conv.user1_id, conv.user2_id]:
        emit("error", {"message": "Unauthorized."})
        return

    # Save message to database
    msg = Message(
        conversation_id=conv_id,
        sender_id=current_user.id,
        message_type="text",
        message_text=text,
    )
    db.session.add(msg)
    db.session.commit()

    # Emit to EVERYONE in the conversation room (including sender for confirmation)
    emit("new_message", msg.to_dict(), room=f"conv_{conv_id}")

    # Also notify the OTHER user's personal room so their sidebar updates
    other_id = conv.user2_id if conv.user1_id == current_user.id else conv.user1_id
    emit("conversation_updated", {
        "conversation_id": conv_id,
        "last_message": msg.to_dict(),
    }, room=f"user_{other_id}")


@socketio.on("media_sent")
def handle_media_sent(data):
    """
    After a media file is uploaded via HTTP (POST /api/.../send_media),
    the browser emits this event so we can broadcast to the conversation room.
    We look up the message by ID (created by the HTTP route) and emit it.
    """
    if not current_user.is_authenticated:
        return

    msg_id  = data.get("message_id")
    conv_id = data.get("conversation_id")

    if not msg_id or not conv_id:
        return

    msg = db.session.get(Message, msg_id)
    if not msg or msg.sender_id != current_user.id:
        return

    # Broadcast the message to the conversation room
    emit("new_message", msg.to_dict(), room=f"conv_{conv_id}")

    # Notify the other user's sidebar
    conv = db.session.get(Conversation, conv_id)
    if conv:
        other_id = conv.user2_id if conv.user1_id == current_user.id else conv.user1_id
        emit("conversation_updated", {
            "conversation_id": conv_id,
            "last_message": msg.to_dict(),
        }, room=f"user_{other_id}")


@socketio.on("typing")
def handle_typing(data):
    """
    Broadcast a typing indicator to the other user.
    The browser emits this while the user is typing.
    """
    if not current_user.is_authenticated:
        return

    conv_id = data.get("conversation_id")
    is_typing = data.get("is_typing", False)

    conv = db.session.get(Conversation, conv_id)
    if not conv or current_user.id not in [conv.user1_id, conv.user2_id]:
        return

    # Emit to conversation room (everyone EXCEPT the sender will get it)
    emit("typing_indicator", {
        "user_id": current_user.id,
        "username": current_user.username,
        "is_typing": is_typing,
        "conversation_id": conv_id,
    }, room=f"conv_{conv_id}", include_self=False)


@socketio.on("message_read")
def handle_message_read(data):
    """Tell the sender that their messages have been read."""
    if not current_user.is_authenticated:
        return

    conv_id = data.get("conversation_id")
    conv = db.session.get(Conversation, conv_id)
    if not conv or current_user.id not in [conv.user1_id, conv.user2_id]:
        return

    other_id = conv.user2_id if conv.user1_id == current_user.id else conv.user1_id

    # Notify the other person their messages were read
    emit("messages_read", {
        "conversation_id": conv_id,
        "read_by": current_user.id,
    }, room=f"user_{other_id}")


# ---------------------------------------------------------------------------
# 7. Run the Server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting ChatSpace server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server.\n")

    # debug=True auto-reloads when you save changes (great for development)
    # use_reloader=False is required because SocketIO + debug reloader can conflict
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
