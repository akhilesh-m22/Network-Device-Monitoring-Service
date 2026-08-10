"""Background monitoring service.

A daemon thread periodically walks through every registered device and
performs a reachability check. Results are written to the devices table
(current status, response time, counters) and to the monitoring_history
table so the user can inspect past checks.

The thread is started by the Flask app factory and runs for the lifetime
of the process. Tests can call ``check_device`` directly without starting
the thread.
"""

import logging
import threading
from datetime import datetime

from app import db
from app.models import Device, MonitoringHistory
from app.utils import ping_device

logger = logging.getLogger("monitor")


class MonitorService(threading.Thread):
    """Runs monitoring checks in the background on a loop."""

    def __init__(self, app, check_interval=None):
        super().__init__(daemon=True, name="monitor-thread")
        self.app = app
        self.check_interval = check_interval or app.config.get(
            "MONITOR_CHECK_INTERVAL", 10
        )
        self._stop_event = threading.Event()

    def run(self):
        """Thread body: check all devices, sleep, repeat until stopped."""
        while not self._stop_event.is_set():
            try:
                self.check_all_devices()
            except Exception:
                # One failed cycle must not kill the thread.
                logger.exception("Monitoring cycle failed, will retry.")
            self._stop_event.wait(self.check_interval)

    def stop(self):
        """Signal the thread to stop after its current cycle."""
        self._stop_event.set()

    def check_all_devices(self):
        """Run one monitoring cycle for every registered device."""
        # Flask-SQLAlchemy needs an application context to access the DB.
        with self.app.app_context():
            devices = Device.query.all()
            for device in devices:
                self.check_device(device)

    def check_device(self, device):
        """Check a single device, update its health, record history.

        Must be called inside an application context. Never raises: any
        ping failure is treated as DOWN so one broken device cannot stop
        the monitoring service.
        """
        try:
            reachable, response_time = ping_device(
                device.ip_address, self.app.config.get("PING_TIMEOUT_SECONDS", 3)
            )
        except Exception as exc:
            logger.warning("Ping failed for %s: %s", device.ip_address, exc)
            reachable, response_time = False, None

        now = datetime.utcnow()
        device.status = "UP" if reachable else "DOWN"
        device.last_checked = now
        device.response_time_ms = response_time
        if reachable:
            device.successful_checks += 1
        else:
            device.failed_checks += 1

        record = MonitoringHistory(
            device_id=device.id,
            status=device.status,
            response_time=response_time,
            checked_at=now,
        )
        db.session.add(record)

        try:
            db.session.commit()
        except Exception:
            # The device may have been deleted while we were checking it.
            db.session.rollback()
            logger.exception("Could not save check result for device %s", device.id)
