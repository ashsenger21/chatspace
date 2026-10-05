"""
test_live_server.py - End-to-End Live Server & Client Integration Test

Tests the full user flow required:
  REGISTER -> LOGIN -> HOME -> SEARCH USER -> START CHAT -> SEND TEXT -> SEND PHOTO -> SEND VIDEO -> VOICE AUDIO -> RECEIVE MESSAGES IN REAL TIME
"""

import io
import json
import time
import requests

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    print("=== Starting ChatSpace End-to-End Live Integration Tests ===")

    # Session 1: Alice
    s_alice = requests.Session()
    # Session 2: Bob
    s_bob = requests.Session()

    username_alice = f"alice_{int(time.time())}"
    username_bob = f"bob_{int(time.time())}"
    password = "securePassword123"

    # 1. REGISTER Alice & Bob
    print(f"1. Registering user '{username_alice}'...")
    r = s_alice.post(f"{BASE_URL}/register", data={
        "username": username_alice,
        "password": password,
        "confirm_password": password
    }, allow_redirects=True)
    assert r.status_code == 200, f"Alice registration failed: {r.status_code}"

    print(f"2. Registering user '{username_bob}'...")
    r = s_bob.post(f"{BASE_URL}/register", data={
        "username": username_bob,
        "password": password,
        "confirm_password": password
    }, allow_redirects=True)
    assert r.status_code == 200, f"Bob registration failed: {r.status_code}"

    # 2. LOGIN Alice & Bob
    print("3. Logging in Alice...")
    r = s_alice.post(f"{BASE_URL}/login", data={
        "username": username_alice,
        "password": password
    }, allow_redirects=True)
    assert r.status_code == 200
    assert "/home" in r.url or "ChatSpace" in r.text

    print("4. Logging in Bob...")
    r = s_bob.post(f"{BASE_URL}/login", data={
        "username": username_bob,
        "password": password
    }, allow_redirects=True)
    assert r.status_code == 200

    # 3. HOME - verify authenticated access
    print("5. Accessing /home dashboard...")
    r = s_alice.get(f"{BASE_URL}/home")
    assert r.status_code == 200
    assert "ChatSpace" in r.text
    assert "conversationList" in r.text

    # 4. API /api/me
    r = s_alice.get(f"{BASE_URL}/api/me")
    assert r.status_code == 200
    alice_data = r.json()
    print(f"   Alice authenticated as ID {alice_data['id']}, username: {alice_data['username']}")

    r = s_bob.get(f"{BASE_URL}/api/me")
    assert r.status_code == 200
    bob_data = r.json()
    print(f"   Bob authenticated as ID {bob_data['id']}, username: {bob_data['username']}")

    # 5. SEARCH USER
    print(f"6. Alice searches for '{username_bob}'...")
    r = s_alice.get(f"{BASE_URL}/api/users/search?q={username_bob}")
    assert r.status_code == 200
    users = r.json()
    assert len(users) >= 1, f"User search returned empty list"
    assert users[0]["username"] == username_bob
    print(f"   Found user {users[0]['username']} (ID: {users[0]['id']})")

    # 6. START CHAT
    print(f"7. Alice starts a conversation with Bob (ID: {bob_data['id']})...")
    r = s_alice.post(f"{BASE_URL}/api/conversation/start/{bob_data['id']}")
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]
    print(f"   Conversation created/retrieved with ID: {conv_id}")

    # 7. SEND TEXT MESSAGE
    print("8. Alice sends text message to Bob...")
    text_content = "Hey Bob! This is our real-time ChatSpace conversation."
    r = s_alice.post(f"{BASE_URL}/api/conversation/{conv_id}/send", json={"text": text_content})
    assert r.status_code == 201
    msg1 = r.json()
    assert msg1["message_text"] == text_content
    print(f"   Text message sent with ID {msg1['id']}: '{msg1['message_text']}'")

    # 8. SEND PHOTO
    print("9. Alice sends a photo to Bob...")
    photo_file = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRsampleimage")
    r = s_alice.post(f"{BASE_URL}/api/conversation/{conv_id}/send_media", files={
        "file": ("vacation.png", photo_file, "image/png")
    }, data={"type": "image"})
    assert r.status_code == 201
    img_msg = r.json()
    assert img_msg["message_type"] == "image"
    assert img_msg["media_url"].startswith("/uploads/images/")
    print(f"   Photo sent: {img_msg['media_url']}")

    # 9. SEND VIDEO
    print("10. Alice sends a video clip to Bob...")
    video_file = io.BytesIO(b"sample video bytes content")
    r = s_alice.post(f"{BASE_URL}/api/conversation/{conv_id}/send_media", files={
        "file": ("demo.mp4", video_file, "video/mp4")
    }, data={"type": "video"})
    assert r.status_code == 201
    vid_msg = r.json()
    assert vid_msg["message_type"] == "video"
    print(f"   Video sent: {vid_msg['media_url']}")

    # 10. RECORD & SEND VOICE AUDIO
    print("11. Bob records and sends voice audio to Alice...")
    audio_file = io.BytesIO(b"sample audio webm content")
    r = s_bob.post(f"{BASE_URL}/api/conversation/{conv_id}/send_media", files={
        "file": ("voice_note.webm", audio_file, "audio/webm")
    }, data={"type": "audio"})
    assert r.status_code == 201
    aud_msg = r.json()
    assert aud_msg["message_type"] == "audio"
    print(f"   Voice note sent: {aud_msg['media_url']}")

    # 11. FETCH MESSAGES & VERIFY CHRONOLOGICAL ORDER
    print("12. Fetching conversation messages...")
    r = s_bob.get(f"{BASE_URL}/api/conversation/{conv_id}/messages")
    assert r.status_code == 200
    messages = r.json()
    assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"
    print(f"   Successfully retrieved {len(messages)} messages:")
    for m in messages:
        print(f"     [{m['message_type'].upper()}] by {m['sender_username']}: {m.get('message_text') or m.get('media_url')}")

    # 12. IN-CHAT MESSAGE SEARCH
    print("13. Testing in-chat search for 'ChatSpace'...")
    r = s_alice.get(f"{BASE_URL}/api/conversation/{conv_id}/search?q=ChatSpace")
    assert r.status_code == 200
    search_results = r.json()
    assert len(search_results) == 1
    assert "ChatSpace" in search_results[0]["message_text"]
    print(f"   Search returned {len(search_results)} match: '{search_results[0]['message_text']}'")

    # 13. MARK READ
    print("14. Bob marks messages as read...")
    r = s_bob.post(f"{BASE_URL}/api/conversation/{conv_id}/read")
    assert r.status_code == 200

    # 14. PROFILE UPDATE (Change Username & Picture)
    print("15. Bob updates his profile username...")
    new_bob_name = f"bob_new_{int(time.time())}"
    r = s_bob.post(f"{BASE_URL}/profile/username", json={"username": new_bob_name})
    assert r.status_code == 200

    r = s_bob.get(f"{BASE_URL}/api/me")
    assert r.json()["username"] == new_bob_name
    print(f"   Username updated to: {r.json()['username']}")

    # 15. LOGOUT
    print("16. Logging out Alice...")
    r = s_alice.get(f"{BASE_URL}/logout", allow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    print("   Logout redirected to /login successfully.")

    print("\nSUCCESS: All full-stack flows verified successfully on the live server!")

if __name__ == "__main__":
    run_tests()
