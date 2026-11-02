"""
models/user.py - User Database Model

This file defines the User table in our SQLite database.
SQLAlchemy turns this Python class into actual database rows automatically.
"""

from datetime import datetime, timezone
from flask_login import UserMixin
from . import db  # Import db from models/__init__.py


class User(UserMixin, db.Model):
    """
    Represents a registered user.

    UserMixin gives us the standard Flask-Login properties/methods:
      - is_authenticated, is_active, is_anonymous, get_id()
    """

    __tablename__ = "users"

    # Primary key – unique integer auto-incremented for every new user
    id = db.Column(db.Integer, primary_key=True)

    # Username must be unique and non-null (max 80 chars)
    username = db.Column(db.String(80), unique=True, nullable=False)

    # We NEVER store the real password – only a bcrypt hash
    password_hash = db.Column(db.String(256), nullable=False)

    # Optional profile picture filename (stored in uploads/images/)
    profile_picture = db.Column(db.String(256), nullable=True, default=None)

    # When the account was created
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Updated every time the user does something (login, send message, etc.)
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Track if user is currently connected via WebSocket
    is_online = db.Column(db.Boolean, default=False)

    # ---------------------------------------------------------------------------
    # Relationships – SQLAlchemy will automatically join these for us
    # ---------------------------------------------------------------------------

    # Messages this user has sent (one user → many messages)
    sent_messages = db.relationship(
        "Message", foreign_keys="Message.sender_id", backref="sender", lazy="dynamic"
    )

    # Conversations where this user is participant 1
    conversations_as_user1 = db.relationship(
        "Conversation", foreign_keys="Conversation.user1_id", backref="user1", lazy="dynamic"
    )

    # Conversations where this user is participant 2
    conversations_as_user2 = db.relationship(
        "Conversation", foreign_keys="Conversation.user2_id", backref="user2", lazy="dynamic"
    )

    def get_profile_picture_url(self):
        """Return the URL path for the user's profile picture, or a default avatar."""
        if self.profile_picture:
            # Clean up if saved with malformed prefix
            if self.profile_picture.startswith("/uploads/images/http://") or self.profile_picture.startswith("/uploads/images/https://"):
                return self.profile_picture[16:]
            if self.profile_picture.startswith("/uploads/http://") or self.profile_picture.startswith("/uploads/https://"):
                return self.profile_picture[9:]
            # Cloudinary or other absolute URLs should be returned as-is
            if self.profile_picture.startswith("http://") or self.profile_picture.startswith("https://"):
                return self.profile_picture
            if self.profile_picture.startswith("/uploads/"):
                return self.profile_picture
            return f"/uploads/images/{self.profile_picture}"
        return None  # Frontend will generate a default avatar from initials

    def update_last_seen(self):
        """Call this whenever the user performs an action."""
        self.last_seen = datetime.now(timezone.utc)
        db.session.commit()

    def to_dict(self):
        """Convert user to a dictionary for JSON responses."""
        ls_str = None
        if self.last_seen:
            ls_str = self.last_seen.isoformat() + "Z" if self.last_seen.tzinfo is None else self.last_seen.isoformat()

        return {
            "id": self.id,
            "username": self.username,
            "profile_picture": self.get_profile_picture_url(),
            "is_online": self.is_online,
            "last_seen": ls_str,
        }

    def __repr__(self):
        return f"<User {self.username}>"
