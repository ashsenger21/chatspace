"""
routes/chat.py - Chat Routes

Handles all chat-related HTTP endpoints:
  - Home page (conversation list)
  - Starting / opening conversations
  - Sending messages (text + media)
  - Fetching messages for a conversation
  - Searching users / messages
  - Serving uploaded media files securely

Media uploads go to Cloudinary (production) or local disk (development).
"""

import os
import uuid
from datetime import datetime

import cloudinary
import cloudinary.uploader

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app, send_from_directory, abort
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import db
from models.user import User
from models.conversation import Conversation
from models.message import Message

chat_bp = Blueprint("chat", __name__)


# ---------------------------------------------------------------------------
# Utility: configure Cloudinary from app config
# ---------------------------------------------------------------------------
def _setup_cloudinary():
    """Configure the Cloudinary SDK using values from app config."""
    cloudinary.config(
        cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=current_app.config["CLOUDINARY_API_KEY"],
        api_secret=current_app.config["CLOUDINARY_API_SECRET"],
        secure=True,  # Always use HTTPS URLs
    )


# ---------------------------------------------------------------------------
# Utility: validate file extension
# ---------------------------------------------------------------------------
def allowed_file(filename, allowed_extensions):
    """Return True if the file extension is in the allowed set."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in allowed_extensions
    )


# ---------------------------------------------------------------------------
# Utility: upload to Cloudinary OR save locally
# Returns (url_or_path, error_string)
# ---------------------------------------------------------------------------
def save_upload(file, subfolder, allowed_extensions):
    """
    Validate and save an uploaded file.
    - If Cloudinary is configured: upload to cloud, return the secure URL.
    - Otherwise: save to local uploads/ folder, return the relative path.
    """
    if not file or file.filename == "":
        return None, "No file selected."

    if not allowed_file(file.filename, allowed_extensions):
        ext_list = ", ".join(sorted(allowed_extensions))
        return None, f"File type not allowed. Allowed: {ext_list}"

    if current_app.config.get("USE_CLOUDINARY"):
        # --- CLOUDINARY UPLOAD ---
        try:
            _setup_cloudinary()
            # resource_type: image, video, or raw (for audio)
            resource_type = "video" if subfolder == "videos" else (
                "video" if subfolder == "audio" else "image"
            )
            result = cloudinary.uploader.upload(
                file,
                folder=f"chatspace/{subfolder}",
                resource_type=resource_type,
                unique_filename=True,
                overwrite=False,
            )
            # Return the secure Cloudinary URL as the "path"
            return result["secure_url"], None
        except Exception as e:
            return None, f"Upload failed: {str(e)}"
    else:
        # --- LOCAL DISK UPLOAD (development) ---
        original_ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name  = f"{uuid.uuid4().hex}.{original_ext}"

        upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, unique_name)
        file.save(file_path)

        # Return the relative path stored in the DB
        return f"{subfolder}/{unique_name}", None


# ---------------------------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------------------------
@chat_bp.route("/home")
@login_required
def home():
    """Render the main chat dashboard."""
    current_user.update_last_seen()
    return render_template("home.html")


# ---------------------------------------------------------------------------
# API: get all conversations for the current user
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversations")
@login_required
def get_conversations():
    """Return a JSON list of conversations sorted by most recent message."""
    uid = current_user.id

    convs = Conversation.query.filter(
        db.or_(Conversation.user1_id == uid, Conversation.user2_id == uid)
    ).all()

    result = []
    for conv in convs:
        last_msg = conv.messages.order_by(Message.timestamp.desc()).first()
        other    = conv.other_user(uid)
        if not other:
            continue

        result.append({
            "id": conv.id,
            "other_user": other.to_dict(),
            "last_message": last_msg.to_dict() if last_msg else None,
            "unread_count": conv.unread_count(uid),
            "created_at": conv.created_at.isoformat(),
        })

    result.sort(
        key=lambda c: c["last_message"]["timestamp"] if c["last_message"] else c.get("created_at", ""),
        reverse=True
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# API: open / get details for one conversation
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>")
@login_required
def get_conversation(conv_id):
    """Return details for a single conversation."""
    conv = db.get_or_404(Conversation, conv_id)

    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    other = conv.other_user(current_user.id)
    return jsonify({
        "id": conv.id,
        "other_user": other.to_dict(),
    })


# ---------------------------------------------------------------------------
# API: fetch messages for a conversation
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>/messages")
@login_required
def get_messages(conv_id):
    """Return message history. Supports pagination via ?before=<message_id>."""
    conv = db.get_or_404(Conversation, conv_id)

    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    before_id = request.args.get("before", type=int)
    limit     = min(request.args.get("limit", 50, type=int), 100)

    query = conv.messages.order_by(Message.timestamp.desc())
    if before_id:
        pivot = db.session.get(Message, before_id)
        if pivot:
            query = query.filter(Message.timestamp < pivot.timestamp)

    messages = query.limit(limit).all()
    messages.reverse()

    # Mark received messages as read
    conv.messages.filter(
        Message.sender_id != current_user.id,
        Message.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.session.commit()

    return jsonify([m.to_dict() for m in messages])


# ---------------------------------------------------------------------------
# API: send a TEXT message
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>/send", methods=["POST"])
@login_required
def send_message(conv_id):
    """Send a text message to a conversation."""
    conv = db.get_or_404(Conversation, conv_id)

    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    data = request.get_json()
    text = (data or {}).get("text", "").strip()

    if not text:
        return jsonify({"error": "Message cannot be empty."}), 400

    if len(text) > 5000:
        return jsonify({"error": "Message is too long (max 5000 characters)."}), 400

    msg = Message(
        conversation_id=conv_id,
        sender_id=current_user.id,
        message_type="text",
        message_text=text,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify(msg.to_dict()), 201


# ---------------------------------------------------------------------------
# API: send a MEDIA message (image / video / audio)
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>/send_media", methods=["POST"])
@login_required
def send_media(conv_id):
    """Upload a media file and create a message record."""
    conv = db.get_or_404(Conversation, conv_id)

    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    file       = request.files.get("file")
    media_type = request.form.get("type", "image")  # image | video | audio

    type_map = {
        "image": ("images", current_app.config["ALLOWED_IMAGE_EXTENSIONS"]),
        "video": ("videos", current_app.config["ALLOWED_VIDEO_EXTENSIONS"]),
        "audio": ("audio",  current_app.config["ALLOWED_AUDIO_EXTENSIONS"]),
    }

    if media_type not in type_map:
        return jsonify({"error": "Invalid media type."}), 400

    subfolder, allowed_exts = type_map[media_type]
    saved_path, err = save_upload(file, subfolder, allowed_exts)

    if err:
        return jsonify({"error": err}), 400

    msg = Message(
        conversation_id=conv_id,
        sender_id=current_user.id,
        message_type=media_type,
        media_path=saved_path,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify(msg.to_dict()), 201


# ---------------------------------------------------------------------------
# API: start or open a conversation with another user
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/start/<int:other_user_id>", methods=["POST"])
@login_required
def start_conversation(other_user_id):
    """Create (or find) a conversation between the current user and another user."""
    if other_user_id == current_user.id:
        return jsonify({"error": "You cannot start a conversation with yourself."}), 400

    other = db.get_or_404(User, other_user_id)
    conv  = Conversation.get_or_create(current_user.id, other_user_id)

    return jsonify({"conversation_id": conv.id}), 200


# ---------------------------------------------------------------------------
# API: search users (for "New Chat" feature)
# ---------------------------------------------------------------------------
@chat_bp.route("/api/users/search")
@login_required
def search_users():
    """Search registered users by username (excludes current user)."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    users = User.query.filter(
        User.username.ilike(f"%{query}%"),
        User.id != current_user.id
    ).limit(20).all()

    return jsonify([u.to_dict() for u in users])


# ---------------------------------------------------------------------------
# API: search messages inside a conversation
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>/search")
@login_required
def search_messages(conv_id):
    """Full-text search through messages in a conversation."""
    conv = db.get_or_404(Conversation, conv_id)
    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    msgs = conv.messages.filter(
        Message.message_text.ilike(f"%{query}%")
    ).order_by(Message.timestamp.desc()).limit(50).all()

    return jsonify([m.to_dict() for m in msgs])


# ---------------------------------------------------------------------------
# API: mark all messages in a conversation as read
# ---------------------------------------------------------------------------
@chat_bp.route("/api/conversation/<int:conv_id>/read", methods=["POST"])
@login_required
def mark_read(conv_id):
    """Mark all messages sent to the current user as read."""
    conv = db.get_or_404(Conversation, conv_id)
    if current_user.id not in [conv.user1_id, conv.user2_id]:
        abort(403)

    conv.messages.filter(
        Message.sender_id != current_user.id,
        Message.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.session.commit()
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Serve uploaded files (LOCAL only — Cloudinary files are served directly)
# ---------------------------------------------------------------------------
@chat_bp.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    """
    Serve a file from the local uploads directory.
    Only used when Cloudinary is NOT configured (local dev).
    """
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    return send_from_directory(upload_folder, filename)
