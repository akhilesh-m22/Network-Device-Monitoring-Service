"""Database models for devices and their monitoring history."""

from datetime import datetime

from app import db

# Allowed device types. The list is intentionally small so the app stays
# easy to understand; more types can be added later.
ALLOWED_DEVICE_TYPES = ("server", "router", "switch", "workstation")


def format_datetime(value):
    """Format a datetime for JSON output, or None for empty values."""
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


class Device(db.Model):
    """A network device the user wants to monitor."""

    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(255), nullable=False)
    device_type = db.Column(db.String(50), nullable=False, default="server")
    description = db.Column(db.String(255), nullable=False, default="")
    monitoring_interval = db.Column(db.Integer, nullable=False, default=60)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Health information updated by the background monitor thread.
    status = db.Column(db.String(10), nullable=False, default="UNKNOWN")
    last_checked = db.Column(db.DateTime, nullable=True)
    response_time_ms = db.Column(db.Float, nullable=True)
    successful_checks = db.Column(db.Integer, nullable=False, default=0)
    failed_checks = db.Column(db.Integer, nullable=False, default=0)

    # One device has many history records. Deleting a device also deletes
    # its history (cascade) so no orphaned rows remain.
    history = db.relationship(
        "MonitoringHistory",
        backref="device",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        """Convert the device into a dictionary ready for JSON responses."""
        return {
            "id": self.id,
            "name": self.name,
            "ip_address": self.ip_address,
            "device_type": self.device_type,
            "description": self.description,
            "monitoring_interval": self.monitoring_interval,
            "created_at": format_datetime(self.created_at),
            "status": self.status,
            "last_checked": format_datetime(self.last_checked),
            "response_time_ms": self.response_time_ms,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
        }


class MonitoringHistory(db.Model):
    """One row per monitoring check, giving a history for each device."""

    __tablename__ = "monitoring_history"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(
        db.Integer,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = db.Column(db.String(10), nullable=False)
    response_time = db.Column(db.Float, nullable=True)
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        """Convert the history record into a dictionary for JSON responses."""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "status": self.status,
            "response_time": self.response_time,
            "checked_at": format_datetime(self.checked_at),
        }
