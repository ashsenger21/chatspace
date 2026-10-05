"""
routes/auth.py - Authentication Routes

Handles user registration, login, and logout.
Flask Blueprints let us keep routes organised in separate files.
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from models.user import User

# Create a Blueprint named "auth" – all routes defined here will be prefixed
# by whatever prefix we give when registering in app.py (none in this case).
auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Show the registration form (GET) and create a new user (POST)."""

    # If the user is already logged in, send them home
    if current_user.is_authenticated:
        return redirect(url_for("chat.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm_password", "").strip()

        # --- Basic validation ---
        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")

        if len(username) < 3 or len(username) > 30:
            flash("Username must be between 3 and 30 characters.", "error")
            return render_template("register.html")

        # Only alphanumeric + underscores allowed in usernames
        if not username.replace("_", "").isalnum():
            flash("Username can only contain letters, numbers, and underscores.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        # --- Check for duplicate username (case-insensitive) ---
        existing = User.query.filter(
            db.func.lower(User.username) == username.lower()
        ).first()
        if existing:
            flash("That username is already taken. Please choose another.", "error")
            return render_template("register.html")

        # --- Create the new user ---
        new_user = User(
            username=username,
            # generate_password_hash uses pbkdf2:sha256 by default – very secure
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/")
def index():
    """Redirect to home if logged in, otherwise to login page."""
    if current_user.is_authenticated:
        return redirect(url_for("chat.home"))
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Show the login form (GET) and authenticate the user (POST)."""

    if current_user.is_authenticated:
        return redirect(url_for("chat.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please enter both username and password.", "error")
            return render_template("login.html")

        # Look up user (case-insensitive username)
        user = User.query.filter(
            db.func.lower(User.username) == username.lower()
        ).first()

        # check_password_hash compares the provided password against the stored hash
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        # Flask-Login sets a secure session cookie
        login_user(user, remember=True)
        user.update_last_seen()

        # Redirect to the page the user was trying to visit, or home
        next_page = request.args.get("next")
        return redirect(next_page or url_for("chat.home"))

    return render_template("login.html")


# ---------------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------------
@auth_bp.route("/logout")
@login_required
def logout():
    """Log the current user out and redirect to login."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
