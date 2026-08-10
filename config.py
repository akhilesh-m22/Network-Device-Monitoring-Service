"""Application configuration.

Values can be overridden with environment variables so the app can be
configured without changing code (e.g. for tests).
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Used by Flask for sessions. Not a secret used in production.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # SQLite database file lives in the project root.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "network_monitor.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # How often the background monitor thread runs a check cycle (seconds).
    MONITOR_CHECK_INTERVAL = int(os.environ.get("MONITOR_CHECK_INTERVAL", "10"))

    # Per-device ping timeout in seconds. Devices that do not answer within
    # this time are marked DOWN and the monitor moves on to the next device.
    PING_TIMEOUT_SECONDS = int(os.environ.get("PING_TIMEOUT_SECONDS", "3"))

    # Whether the monitoring thread should start with the app. Set to False
    # in tests so the test suite does not run background threads.
    START_MONITORING = True
