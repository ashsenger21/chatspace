"""
routes/profile.py - Profile & Settings Routes

Lets logged-in users update their username, password, and profile picture.
Profile pictures go to Cloudinary (production) or local disk (development).
"""

import os
import uuid

import cloudinary
import cloudinary.uploader

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db
from models.user import User

profile_bp = Blueprint("profile", __name__)


def allowed_image(filename):
    """Check if the file is an allowed image type."""
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _setup_cloudinary():
    """Configure Cloudinary SDK from app config."""
    cloudinary.config(
        cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=current_app.config["CLOUDINARY_API_KEY"],
        api_secret=current_app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )


# ---------------------------------------------------------------------------
# Profile Page
# ---------------------------------------------------------------------------
@profile_bp.route("/profile")
@login_required
def profile():
    """Render the profile/settings page."""
    return render_template("profile.html")


# ---------------------------------------------------------------------------
# Update Username
# ---------------------------------------------------------------------------
@profile_bp.route("/profile/username", methods=["POST"])
@login_required
def update_username():
    """Change the current user's username."""
    data         = request.get_json()
    new_username = (data or {}).get("username", "").strip()

    if not new_username:
        return jsonify({"error": "Username cannot be empty."}), 400

    if len(new_username) < 3 or len(new_username) > 30:
        return jsonify({"error": "Username must be 3–30 characters."}), 400

    if not new_username.replace("_", "").isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, and underscores."}), 400

    existing = User.query.filter(
        db.func.lower(User.username) == new_username.lower(),
        User.id != current_user.id
    ).first()

    if existing:
        return jsonify({"error": "That username is already taken."}), 409

    current_user.username = new_username
    db.session.commit()
    return jsonify({"message": "Username updated!", "username": new_username})


# ---------------------------------------------------------------------------
# Update Password
# ---------------------------------------------------------------------------
@profile_bp.route("/profile/password", methods=["POST"])
@login_required
def update_password():
    """Change the current user's password."""
    data       = request.get_json()
    current_pw = (data or {}).get("current_password", "")
    new_pw     = (data or {}).get("new_password", "")
    confirm_pw = (data or {}).get("confirm_password", "")

    if not check_password_hash(current_user.password_hash, current_pw):
        return jsonify({"error": "Current password is incorrect."}), 400

    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400

    if new_pw != confirm_pw:
        return jsonify({"error": "New passwords do not match."}), 400

    current_user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    return jsonify({"message": "Password updated successfully!"})


# ---------------------------------------------------------------------------
# Upload Profile Picture
# ---------------------------------------------------------------------------
@profile_bp.route("/profile/picture", methods=["POST"])
@login_required
def update_picture():
    """Upload a new profile picture to Cloudinary or local disk."""
    file = request.files.get("picture")

    if not file or file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_image(file.filename):
        return jsonify({"error": "Only JPG, JPEG, PNG, GIF, WEBP images are allowed."}), 400

    if current_app.config.get("USE_CLOUDINARY"):
        # --- Upload to Cloudinary ---
        try:
            _setup_cloudinary()
            result = cloudinary.uploader.upload(
                file,
                folder="chatspace/profiles",
                public_id=f"user_{current_user.id}",  # Overwrites old picture automatically
                overwrite=True,
                resource_type="image",
            )
            picture_url = result["secure_url"]
            # Store the Cloudinary URL directly as profile_picture
            current_user.profile_picture = picture_url
            db.session.commit()
            return jsonify({"message": "Profile picture updated!", "picture_url": picture_url})
        except Exception as e:
            return jsonify({"error": f"Upload failed: {str(e)}"}), 500
    else:
        # --- Save locally ---
        ext         = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"profile_{current_user.id}_{uuid.uuid4().hex}.{ext}"
        save_dir    = os.path.join(current_app.config["UPLOAD_FOLDER"], "images")
        os.makedirs(save_dir, exist_ok=True)

        # Delete old picture if it's a local file (not a URL)
        if current_user.profile_picture and not current_user.profile_picture.startswith("http"):
            old_path = os.path.join(save_dir, current_user.profile_picture)
            if os.path.exists(old_path):
                os.remove(old_path)

        file.save(os.path.join(save_dir, unique_name))
        current_user.profile_picture = unique_name
        db.session.commit()

        return jsonify({
            "message": "Profile picture updated!",
            "picture_url": f"/uploads/images/{unique_name}"
        })


# ---------------------------------------------------------------------------
# Get current user info (API)
# ---------------------------------------------------------------------------
@profile_bp.route("/api/me")
@login_required
def me():
    """Return the current user's info as JSON."""
    current_user.update_last_seen()
    return jsonify(current_user.to_dict())
