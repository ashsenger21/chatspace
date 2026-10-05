"""
models/conversation.py - Conversation (Chat) Database Model

A conversation is a 1-on-1 chat between two users.
The design keeps user1_id < user2_id to guarantee uniqueness
(so there's only ever ONE conversation record between two users).

To support group chats in the future, you would add an `is_group` flag,
a `name` column, and a separate GroupMembers table.
"""

from datetime import datetime, timezone
import sqlalchemy as sa
from . import db


class Conversation(db.Model):
    """Represents a private conversation between two users."""

    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)

    # We always store the lower user ID as user1 to prevent duplicates
    # (e.g. user 3 <-> user 7 is always stored as user1=3, user2=7, never 7,3)
    user1_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Future group-chat upgrade hook:
    # is_group   = db.Column(db.Boolean, default=False)
    # group_name = db.Column(db.String(120), nullable=True)

    # Unique constraint: exactly one conversation row per user pair
    __table_args__ = (
        db.UniqueConstraint("user1_id", "user2_id", name="uq_conversation_pair"),
    )

    # One conversation -> many messages
    messages = db.relationship(
        "Message", backref="conversation", lazy="dynamic", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_create(user_a_id, user_b_id):
        """
        Find an existing conversation between two users, or create one.
        Always stores the smaller ID as user1 to enforce uniqueness.
        """
        u1, u2 = sorted([user_a_id, user_b_id])
        conv = Conversation.query.filter_by(user1_id=u1, user2_id=u2).first()
        if not conv:
            conv = Conversation(user1_id=u1, user2_id=u2)
            db.session.add(conv)
            db.session.commit()
        return conv

    def other_user(self, current_user_id):
        """Return the User object of the OTHER participant in this conversation."""
        from .user import User
        other_id = self.user2_id if self.user1_id == current_user_id else self.user1_id
        return db.session.get(User, other_id)

    def last_message(self):
        """Return the most recent Message in this conversation, or None."""
        from .message import Message
        return self.messages.order_by(sa.desc(Message.timestamp)).first()

    def unread_count(self, for_user_id):
        """Count messages NOT sent by `for_user_id` that haven't been read yet."""
        from .message import Message
        return self.messages.filter(
            Message.sender_id != for_user_id,
            Message.is_read == False  # noqa: E712
        ).count()

    def to_dict(self, current_user_id):
        """Serialize the conversation for a JSON response."""
        from .message import Message
        other    = self.other_user(current_user_id)
        last_msg = self.messages.order_by(sa.desc(Message.timestamp)).first()

        return {
            "id": self.id,
            "other_user": other.to_dict() if other else None,
            "last_message": last_msg.to_dict() if last_msg else None,
            "unread_count": self.unread_count(current_user_id),
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<Conversation {self.user1_id} <-> {self.user2_id}>"
