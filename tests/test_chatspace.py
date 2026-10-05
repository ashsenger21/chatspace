"""
test_chatspace.py - Comprehensive Test Suite for ChatSpace

Tests:
  - User registration & authentication (validation, duplicate rejection, hashing)
  - Login, logout, session management, route protection
  - User search & conversation creation
  - Text messaging, message retrieval, message search, pagination
  - Media upload (image, video, audio) & extension validation
  - Profile updates (username, password, picture)
  - SocketIO real-time events (connect, send_message, typing, join_conversation)
"""

import io
import os
import unittest
import tempfile
import shutil

from app import app, socketio
from models import db
from models.user import User
from models.conversation import Conversation
from models.message import Message


class ChatSpaceTestCase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.upload_dir = os.path.join(self.test_dir, "uploads")
        os.makedirs(os.path.join(self.upload_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(self.upload_dir, "videos"), exist_ok=True)
        os.makedirs(os.path.join(self.upload_dir, "audio"), exist_ok=True)

        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{self.db_path}"
        app.config["UPLOAD_FOLDER"] = self.upload_dir

        self.client = app.test_client()

        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. Registration Tests
    # -------------------------------------------------------------
    def test_registration_success(self):
        res = self.client.post("/register", data={
            "username": "john_doe",
            "password": "password123",
            "confirm_password": "password123"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with app.app_context():
            user = User.query.filter_by(username="john_doe").first()
            self.assertIsNotNone(user)
            self.assertNotEqual(user.password_hash, "password123")
            self.assertTrue(user.password_hash.startswith("scrypt:") or user.password_hash.startswith("pbkdf2:"))

    def test_registration_duplicate_username(self):
        self.client.post("/register", data={
            "username": "john_doe",
            "password": "password123",
            "confirm_password": "password123"
        })
        # Try registering with same username (case-insensitive)
        res = self.client.post("/register", data={
            "username": "JOHN_DOE",
            "password": "differentpass",
            "confirm_password": "differentpass"
        }, follow_redirects=True)
        self.assertIn(b"already taken", res.data)

    def test_registration_validation(self):
        # Passwords mismatch
        res = self.client.post("/register", data={
            "username": "alice",
            "password": "password123",
            "confirm_password": "wrongpassword"
        }, follow_redirects=True)
        self.assertIn(b"do not match", res.data)

        # Password too short (< 6)
        res = self.client.post("/register", data={
            "username": "alice",
            "password": "123",
            "confirm_password": "123"
        }, follow_redirects=True)
        self.assertIn(b"at least 6 characters", res.data)

        # Invalid username characters
        res = self.client.post("/register", data={
            "username": "invalid user!",
            "password": "password123",
            "confirm_password": "password123"
        }, follow_redirects=True)
        self.assertIn(b"letters, numbers, and underscores", res.data)

    # -------------------------------------------------------------
    # 2. Login, Session & Protected Routes
    # -------------------------------------------------------------
    def test_login_logout_and_protection(self):
        # Unauthenticated user visiting /home redirected to /login
        res = self.client.get("/home", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

        # Register user
        self.client.post("/register", data={
            "username": "testuser",
            "password": "mypassword",
            "confirm_password": "mypassword"
        })

        # Login with wrong password
        res = self.client.post("/login", data={
            "username": "testuser",
            "password": "wrongpassword"
        }, follow_redirects=True)
        self.assertIn(b"Invalid username or password", res.data)

        # Login with correct password
        res = self.client.post("/login", data={
            "username": "testuser",
            "password": "mypassword"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Now /home is accessible
        res = self.client.get("/home")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"ChatSpace", res.data)

        # Logout
        res = self.client.get("/logout", follow_redirects=True)
        self.assertIn(b"logged out", res.data)

        # Accessing /home again redirects
        res = self.client.get("/home", follow_redirects=False)
        self.assertEqual(res.status_code, 302)

    # -------------------------------------------------------------
    # 3. User Search & Conversations
    # -------------------------------------------------------------
    def test_user_search_and_conversation(self):
        # Create user A & B
        self.client.post("/register", data={"username": "user_a", "password": "pass123", "confirm_password": "pass123"})
        self.client.post("/register", data={"username": "user_b", "password": "pass123", "confirm_password": "pass123"})

        # Login as user_a
        self.client.post("/login", data={"username": "user_a", "password": "pass123"})

        # Search for user_b
        res = self.client.get("/api/users/search?q=user_b")
        users = res.get_json()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "user_b")
        user_b_id = users[0]["id"]

        # Search excludes self
        res = self.client.get("/api/users/search?q=user_a")
        users = res.get_json()
        self.assertEqual(len(users), 0)

        # Start conversation with user_b
        res = self.client.post(f"/api/conversation/start/{user_b_id}")
        self.assertEqual(res.status_code, 200)
        conv_id = res.get_json()["conversation_id"]

        # Starting again returns the same conversation (idempotent)
        res2 = self.client.post(f"/api/conversation/start/{user_b_id}")
        self.assertEqual(res2.get_json()["conversation_id"], conv_id)

        # Cannot chat with oneself
        me_res = self.client.get("/api/me")
        me_id = me_res.get_json()["id"]
        res_self = self.client.post(f"/api/conversation/start/{me_id}")
        self.assertEqual(res_self.status_code, 400)

    # -------------------------------------------------------------
    # 4. Messaging & In-Chat Search
    # -------------------------------------------------------------
    def test_messaging_and_search(self):
        # Setup users & conversation
        self.client.post("/register", data={"username": "alice", "password": "password123", "confirm_password": "password123"})
        self.client.post("/register", data={"username": "bob", "password": "password123", "confirm_password": "password123"})
        self.client.post("/login", data={"username": "alice", "password": "password123"})

        res = self.client.get("/api/users/search?q=bob")
        bob_id = res.get_json()[0]["id"]
        res = self.client.post(f"/api/conversation/start/{bob_id}")
        conv_id = res.get_json()["conversation_id"]

        # Send empty message -> error
        res = self.client.post(f"/api/conversation/{conv_id}/send", json={"text": "   "})
        self.assertEqual(res.status_code, 400)

        # Send valid message
        res = self.client.post(f"/api/conversation/{conv_id}/send", json={"text": "Hello Bob, welcome to ChatSpace!"})
        self.assertEqual(res.status_code, 201)
        msg_id = res.get_json()["id"]

        # Send second message
        self.client.post(f"/api/conversation/{conv_id}/send", json={"text": "How is the weather today?"})

        # Fetch messages
        res = self.client.get(f"/api/conversation/{conv_id}/messages")
        msgs = res.get_json()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["message_text"], "Hello Bob, welcome to ChatSpace!")

        # In-chat search
        res = self.client.get(f"/api/conversation/{conv_id}/search?q=weather")
        results = res.get_json()
        self.assertEqual(len(results), 1)
        self.assertIn("weather", results[0]["message_text"])

        # Mark read
        res = self.client.post(f"/api/conversation/{conv_id}/read")
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------
    # 5. Media Uploads (Image, Video, Audio)
    # -------------------------------------------------------------
    def test_media_uploads(self):
        self.client.post("/register", data={"username": "media_user1", "password": "password123", "confirm_password": "password123"})
        self.client.post("/register", data={"username": "media_user2", "password": "password123", "confirm_password": "password123"})
        self.client.post("/login", data={"username": "media_user1", "password": "password123"})

        res = self.client.get("/api/users/search?q=media_user2")
        user2_id = res.get_json()[0]["id"]
        res = self.client.post(f"/api/conversation/start/{user2_id}")
        conv_id = res.get_json()["conversation_id"]

        # 1. Upload valid image
        img_data = (io.BytesIO(b"\x89PNG\r\n\x1a\nfake image content"), "photo.png")
        res = self.client.post(
            f"/api/conversation/{conv_id}/send_media",
            data={"file": img_data, "type": "image"},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["message_type"], "image")
        self.assertTrue(data["media_url"].startswith("/uploads/images/"))

        # 2. Upload valid video
        video_data = (io.BytesIO(b"fake mp4 video content"), "clip.mp4")
        res = self.client.post(
            f"/api/conversation/{conv_id}/send_media",
            data={"file": video_data, "type": "video"},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["message_type"], "video")

        # 3. Upload valid audio
        audio_data = (io.BytesIO(b"fake webm audio content"), "voice.webm")
        res = self.client.post(
            f"/api/conversation/{conv_id}/send_media",
            data={"file": audio_data, "type": "audio"},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["message_type"], "audio")

        # 4. Reject invalid file extension (e.g. .exe)
        bad_file = (io.BytesIO(b"executable payload"), "danger.exe")
        res = self.client.post(
            f"/api/conversation/{conv_id}/send_media",
            data={"file": bad_file, "type": "image"},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("not allowed", res.get_json()["error"])

    # -------------------------------------------------------------
    # 6. Profile Updates
    # -------------------------------------------------------------
    def test_profile_updates(self):
        self.client.post("/register", data={"username": "profile_user", "password": "oldpassword123", "confirm_password": "oldpassword123"})
        self.client.post("/login", data={"username": "profile_user", "password": "oldpassword123"})

        # Change username
        res = self.client.post("/profile/username", json={"username": "new_profile_user"})
        self.assertEqual(res.status_code, 200)

        # Verify change
        res = self.client.get("/api/me")
        self.assertEqual(res.get_json()["username"], "new_profile_user")

        # Change password
        res = self.client.post("/profile/password", json={
            "current_password": "oldpassword123",
            "new_password": "brandnewpassword",
            "confirm_password": "brandnewpassword"
        })
        self.assertEqual(res.status_code, 200)

        # Relogin with new password
        self.client.get("/logout")
        res = self.client.post("/login", data={"username": "new_profile_user", "password": "brandnewpassword"}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Upload profile picture
        pic_data = (io.BytesIO(b"\xff\xd8\xfffake jpg data"), "avatar.jpg")
        res = self.client.post("/profile/picture", data={"picture": pic_data}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        self.assertIn("picture_url", res.get_json())

    # -------------------------------------------------------------
    # 7. WebSocket Events
    # -------------------------------------------------------------
    def test_socketio_realtime(self):
        self.client.post("/register", data={"username": "ws_user1", "password": "password123", "confirm_password": "password123"})
        self.client.post("/register", data={"username": "ws_user2", "password": "password123", "confirm_password": "password123"})
        self.client.post("/login", data={"username": "ws_user1", "password": "password123"})

        res = self.client.get("/api/users/search?q=ws_user2")
        user2_id = res.get_json()[0]["id"]
        res = self.client.post(f"/api/conversation/start/{user2_id}")
        conv_id = res.get_json()["conversation_id"]

        # Create SocketIO test client with logged in session
        sio_client = socketio.test_client(app, flask_test_client=self.client)
        self.assertTrue(sio_client.is_connected())

        # Join conversation
        sio_client.emit("join_conversation", {"conversation_id": conv_id})
        received = sio_client.get_received()
        joined_events = [e for e in received if e["name"] == "joined_conversation"]
        self.assertTrue(len(joined_events) > 0)

        # Send message via WebSocket
        sio_client.emit("send_message", {
            "conversation_id": conv_id,
            "text": "Real-time message through WebSocket!"
        })

        received = sio_client.get_received()
        msg_events = [e for e in received if e["name"] == "new_message"]
        self.assertTrue(len(msg_events) > 0)
        self.assertEqual(msg_events[0]["args"][0]["message_text"], "Real-time message through WebSocket!")

        # Typing indicator
        sio_client.emit("typing", {"conversation_id": conv_id, "is_typing": True})

        sio_client.disconnect()


if __name__ == "__main__":
    unittest.main()
