"""
models/__init__.py - Database Initialization

This file creates the SQLAlchemy `db` object that is shared across all models.
We import it here so that other files can do `from models import db` cleanly.
"""

from flask_sqlalchemy import SQLAlchemy

# Create the SQLAlchemy database instance
# (It's not connected to a Flask app yet – that happens in app.py via db.init_app())
db = SQLAlchemy()
