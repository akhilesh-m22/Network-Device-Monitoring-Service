"""HTTP routes: the dashboard page and the JSON REST API."""

from flask import Blueprint, current_app, jsonify, render_template, request

from app import db
from app.models import ALLOWED_DEVICE_TYPES, Device, MonitoringHistory
from app.utils import validate_ip_or_hostname

main_bp = Blueprint("main", __name__)

# --------------------------- Web dashboard ---------------------------


@main_bp.route("/")
def dashboard():
    return render_template("dashboard.html")


# --------------------------- API helpers ---------------------------

def _get_device_or_404(device_id):
    """Fetch a device by id, or return a JSON 404 response."""
    device = db.session.get(Device, device_id)
    if device is None:
        return None, jsonify(error="Device not found."), 404
    return device, None, None


def _validate_payload(data, require_name, require_ip):
    """Validate incoming JSON, return (cleaned_data, error_response).

    Returns (data, None) on success and (None, (json, status)) on failure.
    """
    errors = []
    cleaned = {}

    name = data.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            errors.append("Device name cannot be empty.")
        elif len(name) > 120:
            errors.append("Device name must be at most 120 characters.")
        else:
            cleaned["name"] = name
    elif require_name:
        errors.append("Missing required field: name.")

    ip_address = data.get("ip_address")
    if ip_address is not None:
        try:
            cleaned["ip_address"] = validate_ip_or_hostname(ip_address)
        except ValueError as exc:
            errors.append(str(exc))
    elif require_ip:
        errors.append("Missing required field: ip_address.")

    device_type = data.get("device_type")
    if device_type is not None:
        device_type = str(device_type).strip().lower()
        if device_type not in ALLOWED_DEVICE_TYPES:
            errors.append(
                "Invalid device type. Allowed: " + ", ".join(ALLOWED_DEVICE_TYPES) + "."
            )
        else:
            cleaned["device_type"] = device_type

    description = data.get("description")
    if description is not None:
        description = str(description).strip()
        if len(description) > 255:
            errors.append("Description must be at most 255 characters.")
        else:
            cleaned["description"] = description

    interval = data.get("monitoring_interval")
    if interval is not None:
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            errors.append("Monitoring interval must be a whole number of seconds.")
        else:
            if interval < 5:
                errors.append("Monitoring interval must be at least 5 seconds.")
            else:
                cleaned["monitoring_interval"] = interval

    if errors:
        return None, jsonify(error="; ".join(errors)), 400
    return cleaned, None, None


# --------------------------- Device CRUD ---------------------------


@main_bp.route("/api/devices", methods=["GET"])
def list_devices():
    devices = Device.query.order_by(Device.id).all()
    return jsonify([device.to_dict() for device in devices])


@main_bp.route("/api/devices/<int:device_id>", methods=["GET"])
def get_device(device_id):
    device, error_response, status = _get_device_or_404(device_id)
    if device is None:
        return error_response, status
    return jsonify(device.to_dict())


@main_bp.route("/api/devices", methods=["POST"])
def create_device():
    data, error_response = _read_json_body()
    if error_response is not None:
        return error_response

    cleaned, error_response, status = _validate_payload(
        data, require_name=True, require_ip=True
    )
    if error_response is not None:
        return error_response, status

    device = Device(
        name=cleaned["name"],
        ip_address=cleaned["ip_address"],
        device_type=cleaned.get("device_type", "server"),
        description=cleaned.get("description", ""),
        monitoring_interval=cleaned.get("monitoring_interval", 60),
    )
    db.session.add(device)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify(error="Database error: " + str(exc)), 500

    return jsonify(device.to_dict()), 201


@main_bp.route("/api/devices/<int:device_id>", methods=["PUT"])
def update_device(device_id):
    device, error_response, status = _get_device_or_404(device_id)
    if device is None:
        return error_response, status

    data, error_response = _read_json_body()
    if error_response is not None:
        return error_response

    # Partial updates are allowed: only the fields present in the body change.
    cleaned, error_response, status = _validate_payload(
        data, require_name=False, require_ip=False
    )
    if error_response is not None:
        return error_response, status

    for field, value in cleaned.items():
        setattr(device, field, value)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify(error="Database error: " + str(exc)), 500

    return jsonify(device.to_dict())


@main_bp.route("/api/devices/<int:device_id>", methods=["DELETE"])
def delete_device(device_id):
    device, error_response, status = _get_device_or_404(device_id)
    if device is None:
        return error_response, status

    db.session.delete(device)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify(error="Database error: " + str(exc)), 500

    return jsonify(message="Device deleted.")


# --------------------------- Monitoring data ---------------------------


@main_bp.route("/api/devices/<int:device_id>/status", methods=["GET"])
def device_status(device_id):
    device, error_response, status = _get_device_or_404(device_id)
    if device is None:
        return error_response, status

    last_history = (
        MonitoringHistory.query.filter_by(device_id=device.id)
        .order_by(MonitoringHistory.checked_at.desc())
        .first()
    )
    return jsonify(
        {
            "device_id": device.id,
            "name": device.name,
            "ip_address": device.ip_address,
            "status": device.status,
            "response_time_ms": device.response_time_ms,
            "last_checked": device.to_dict()["last_checked"],
            "successful_checks": device.successful_checks,
            "failed_checks": device.failed_checks,
            "latest_history": last_history.to_dict() if last_history else None,
        }
    )


@main_bp.route("/api/devices/<int:device_id>/history", methods=["GET"])
def device_history(device_id):
    device, error_response, status = _get_device_or_404(device_id)
    if device is None:
        return error_response, status

    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        return jsonify(error="limit must be a whole number."), 400

    records = (
        MonitoringHistory.query.filter_by(device_id=device.id)
        .order_by(MonitoringHistory.checked_at.desc())
        .limit(max(limit, 1))
        .all()
    )
    return jsonify([record.to_dict() for record in records])


@main_bp.route("/api/health", methods=["GET"])
def health():
    total = Device.query.count()
    up = Device.query.filter_by(status="UP").count()
    down = Device.query.filter_by(status="DOWN").count()

    last_check = None
    latest = MonitoringHistory.query.order_by(MonitoringHistory.checked_at.desc()).first()
    if latest is not None:
        last_check = latest.to_dict()["checked_at"]

    return jsonify(
        {
            "status": "ok",
            "total_devices": total,
            "devices_up": up,
            "devices_down": down,
            "last_check": last_check,
            "monitoring_active": current_app.monitor.is_alive(),
        }
    )


# --------------------------- JSON error handlers ---------------------------

def _read_json_body():
    """Parse the JSON request body.

    Returns (data, None) on success, or (None, (json_response, status_code))
    when the body is missing or is not a JSON object.
    """
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify(error="Request body must be valid JSON."), 400)
    if not isinstance(data, dict):
        return None, (jsonify(error="Request body must be a JSON object."), 400)
    return data, None


@main_bp.errorhandler(400)
@main_bp.errorhandler(404)
def handle_http_error(error):
    """Return JSON errors for API requests (dashboard keeps default HTML)."""
    if request.path.startswith("/api"):
        return jsonify(error=error.description or "Bad request."), error.code
    return error


@main_bp.errorhandler(500)
def handle_server_error(error):
    if request.path.startswith("/api"):
        return jsonify(error="Unexpected server error."), 500
    return error
