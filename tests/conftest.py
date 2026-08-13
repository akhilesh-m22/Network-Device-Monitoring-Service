"""Shared pytest fixtures.

Every test gets its own app with a fresh temporary SQLite database and
monitoring disabled, so tests are isolated and never depend on the network.
"""

import pytest

from app import create_app, db
from app.models import Device
from config import Config


@pytest.fixture()
def app(tmp_path):
    """Create the Flask app with a fresh temporary database per test."""
    test_db_path = tmp_path / "test.db"

    class TestConfig(Config):
        TESTING = True
        START_MONITORING = False  # no background thread in tests
        MONITOR_CHECK_INTERVAL = 1
        PING_TIMEOUT_SECONDS = 1
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{test_db_path}"

    app = create_app(TestConfig)
    yield app
    app.monitor.stop()


@pytest.fixture()
def client(app):
    """Test client used to call the API like a real HTTP client."""
    return app.test_client()


@pytest.fixture()
def sample_device(app):
    """Create a device directly in the database (no API call)."""
    with app.app_context():
        device = Device(
            name="test-server",
            ip_address="127.0.0.1",
            device_type="server",
            description="test device",
            monitoring_interval=60,
        )
        db.session.add(device)
        db.session.commit()
        db.session.refresh(device)
        return device


def create_device_via_api(client, **overrides):
    """Helper: POST a valid device and return (response, data)."""
    payload = {
        "name": "web-server",
        "ip_address": "192.168.1.10",
        "device_type": "server",
        "description": "main web server",
        "monitoring_interval": 60,
    }
    payload.update(overrides)
    response = client.post("/api/devices", json=payload)
    return response, response.get_json()
