"""
models/message.py - Message Database Model

Every chat message (text, image, video, or audio) is stored as a row here.
The `message_type` column tells the frontend HOW to render it.
"""

from datetime import datetime, timezone
from . import db


class Message(db.Model):
    """Represents a single message in a conversation."""

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)

    # Which conversation does this message belong to?
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False
    )

    # Who sent this message?
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Type of message – controls how the frontend renders it
    # Options: "text", "image", "video", "audio"
    message_type = db.Column(db.String(20), nullable=False, default="text")

    # For text messages – the actual message content
    message_text = db.Column(db.Text, nullable=True)

    # For media messages – filename of the uploaded file (relative to uploads/)
    media_path = db.Column(db.String(512), nullable=True)

    # When was this message sent?
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Has the recipient read this message?
    is_read = db.Column(db.Boolean, default=False)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def get_media_url(self):
        """Return the URL for this message's media file."""
        if not self.media_path:
            return None
        return f"/uploads/{self.media_path}"

    def to_dict(self):
        """Serialize the message for JSON API responses and WebSocket events."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "sender_username": self.sender.username if self.sender else "Unknown",
            "sender_picture": self.sender.get_profile_picture_url() if self.sender else None,
            "message_type": self.message_type,
            "message_text": self.message_text,
            "media_url": self.get_media_url(),
            "timestamp": self.timestamp.isoformat(),
            "is_read": self.is_read,
        }

    def __repr__(self):
        return f"<Message {self.id} [{self.message_type}] by user {self.sender_id}>"
