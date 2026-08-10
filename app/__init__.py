"""Application factory for the Network Device Monitoring Service."""

import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from config import Config

# Shared SQLAlchemy instance, used by the models.
db = SQLAlchemy()


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from app import models  # noqa: F401 - registers models with SQLAlchemy
    from app.routes import main_bp

    app.register_blueprint(main_bp)

    # Create the SQLite database and tables if they do not exist yet.
    with app.app_context():
        db.create_all()

    # Start the background monitor thread (unless disabled, e.g. in tests).
    from app.monitor import MonitorService

    app.monitor = MonitorService(app)
    if app.config.get("START_MONITORING", True):
        app.monitor.start()
        logging.getLogger("monitor").info("Monitoring thread started.")

    return app
