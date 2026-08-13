"""Tests for the monitoring logic.

The real ping/subprocess call is mocked (monkeypatched) in every test so
the suite runs offline, on any OS, and never waits on the network.
"""

import subprocess
import time
from types import SimpleNamespace

from app import db
from app.monitor import MonitorService
from app.models import Device, MonitoringHistory
from app.utils import parse_ping_time, ping_device, validate_ip_or_hostname


# --------------------------- input validation ---------------------------


def test_validate_ip_or_hostname_valid():
    assert validate_ip_or_hostname("192.168.1.1") == "192.168.1.1"
    assert validate_ip_or_hostname("8.8.8.8") == "8.8.8.8"
    assert validate_ip_or_hostname("my-server.local") == "my-server.local"
    assert validate_ip_or_hostname("localhost") == "localhost"
    assert validate_ip_or_hostname("Router-1") == "Router-1"


def test_validate_ip_or_hostname_invalid():
    for bad in ["", "999.999.1.1", "not a host!", "2001:db8::1", "a" * 300]:
        try:
            validate_ip_or_hostname(bad)
            assert False, f"should have rejected {bad!r}"
        except ValueError:
            pass


def test_validate_ip_or_hostname_none():
    try:
        validate_ip_or_hostname(None)
        assert False
    except ValueError:
        pass


# --------------------------- ping output parsing ---------------------------


def test_parse_ping_time_windows():
    assert parse_ping_time("Reply from 8.8.8.8: bytes=32 time=14ms TTL=117") == 14.0
    assert parse_ping_time("Reply from 8.8.8.8: time<1ms TTL=64") == 1.0


def test_parse_ping_time_linux():
    assert parse_ping_time("64 bytes: icmp_seq=1 ttl=117 time=14.12 ms") == 14.12


def test_parse_ping_time_missing():
    assert parse_ping_time("Request timed out.") is None


# --------------------------- ping_device (subprocess mocked) ---------------------------


def test_ping_device_windows_command_and_success(monkeypatch):
    called = {}

    def fake_run(command, **kwargs):
        called["command"] = command
        return SimpleNamespace(returncode=0, stdout="Reply from 8.8.8.8: time=12ms")

    monkeypatch.setattr("app.utils.platform.system", lambda: "Windows")
    monkeypatch.setattr("app.utils.subprocess.run", fake_run)

    reachable, response_ms = ping_device("8.8.8.8", timeout=3)
    assert reachable is True
    assert response_ms == 12.0
    # Fixed command structure: no shell, timeout in milliseconds.
    assert called["command"] == ["ping", "-n", "1", "-w", "3000", "8.8.8.8"]


def test_ping_device_linux_command_and_failure(monkeypatch):
    called = {}

    def fake_run(command, **kwargs):
        called["command"] = command
        return SimpleNamespace(returncode=1, stdout="Destination host unreachable")

    monkeypatch.setattr("app.utils.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.utils.subprocess.run", fake_run)

    reachable, response_ms = ping_device("10.0.0.5", timeout=3)
    assert reachable is False
    assert response_ms is None
    assert called["command"] == ["ping", "-c", "1", "-W", "3", "10.0.0.5"]


def test_ping_device_handles_subprocess_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=3)

    monkeypatch.setattr("app.utils.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.utils.subprocess.run", fake_run)

    reachable, response_ms = ping_device("10.0.0.9", timeout=3)
    assert reachable is False
    assert response_ms is None


def test_ping_device_falls_back_to_measured_time(monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="no time field here")

    monkeypatch.setattr("app.utils.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.utils.subprocess.run", fake_run)

    reachable, response_ms = ping_device("10.0.0.1", timeout=3)
    assert reachable is True
    assert response_ms is not None


# --------------------------- check_device ---------------------------


def test_check_device_marks_up(app, sample_device, monkeypatch):
    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (True, 15.5))

    with app.app_context():
        device = db.session.get(Device, sample_device.id)
        app.monitor.check_device(device)

        assert device.status == "UP"
        assert device.response_time_ms == 15.5
        assert device.successful_checks == 1
        assert device.failed_checks == 0
        assert device.last_checked is not None

        history = MonitoringHistory.query.filter_by(device_id=device.id).all()
        assert len(history) == 1
        assert history[0].status == "UP"
        assert history[0].response_time == 15.5


def test_check_device_marks_down(app, sample_device, monkeypatch):
    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (False, None))

    with app.app_context():
        device = db.session.get(Device, sample_device.id)
        app.monitor.check_device(device)

        assert device.status == "DOWN"
        assert device.response_time_ms is None
        assert device.successful_checks == 0
        assert device.failed_checks == 1


def test_check_device_handles_ping_exception(app, sample_device, monkeypatch):
    def boom(host, timeout):
        raise RuntimeError("ping crashed")

    monkeypatch.setattr("app.monitor.ping_device", boom)

    with app.app_context():
        device = db.session.get(Device, sample_device.id)
        # Must not raise: the monitor treats a broken ping as DOWN.
        app.monitor.check_device(device)
        assert device.status == "DOWN"
        assert device.failed_checks == 1


def test_check_all_devices_checks_every_device(app, monkeypatch):
    for name, ip in [("a", "10.0.0.1"), ("b", "10.0.0.2")]:
        with app.app_context():
            db.session.add(Device(name=name, ip_address=ip, device_type="server"))
            db.session.commit()

    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (True, 5.0))
    app.monitor.check_all_devices()

    with app.app_context():
        devices = Device.query.order_by(Device.id).all()
        assert [d.status for d in devices] == ["UP", "UP"]


def test_history_available_through_api_after_check(app, client, sample_device, monkeypatch):
    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (True, 8.0))
    with app.app_context():
        app.monitor.check_device(db.session.get(Device, sample_device.id))

    response = client.get(f"/api/devices/{sample_device.id}/history")
    assert response.status_code == 200
    records = response.get_json()
    assert len(records) == 1
    assert records[0]["status"] == "UP"
    assert records[0]["response_time"] == 8.0


def test_deleting_device_removes_history(app, client, sample_device, monkeypatch):
    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (True, 8.0))
    with app.app_context():
        app.monitor.check_device(db.session.get(Device, sample_device.id))

    response = client.delete(f"/api/devices/{sample_device.id}")
    assert response.status_code == 200

    with app.app_context():
        assert MonitoringHistory.query.count() == 0


# --------------------------- the thread itself ---------------------------


def test_monitor_thread_runs_cycles_and_stops(app, sample_device, monkeypatch):
    monkeypatch.setattr("app.monitor.ping_device", lambda host, timeout: (True, 2.0))

    monitor = MonitorService(app, check_interval=0.2)
    monitor.start()

    try:
        deadline = time.time() + 5
        checked = False
        while time.time() < deadline:
            with app.app_context():
                device = db.session.get(Device, sample_device.id)
                if device is not None and device.status == "UP":
                    checked = True
                    break
            time.sleep(0.1)
        assert checked, "monitor thread never checked the device"
    finally:
        monitor.stop()
        monitor.join(timeout=2)

    assert not monitor.is_alive()
    with app.app_context():
        device = db.session.get(Device, sample_device.id)
        assert device.successful_checks >= 1
        assert (
            MonitoringHistory.query.filter_by(device_id=sample_device.id).count() >= 1
        )
