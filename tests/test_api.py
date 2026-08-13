"""API tests: CRUD operations, validation, errors, and health/status routes."""

from tests.conftest import create_device_via_api

VALID_PAYLOAD = {
    "name": "web-server",
    "ip_address": "192.168.1.10",
    "device_type": "server",
    "description": "main web server",
    "monitoring_interval": 60,
}


# --------------------------- create ---------------------------


def test_create_device(client):
    response, data = create_device_via_api(client)
    assert response.status_code == 201
    assert data["id"] == 1
    assert data["name"] == "web-server"
    assert data["ip_address"] == "192.168.1.10"
    assert data["device_type"] == "server"
    assert data["monitoring_interval"] == 60
    assert data["status"] == "UNKNOWN"
    assert data["created_at"] is not None


def test_create_device_with_hostname(client):
    response, data = create_device_via_api(client, ip_address="my-server.local")
    assert response.status_code == 201
    assert data["ip_address"] == "my-server.local"


def test_create_device_requires_name(client):
    response, data = create_device_via_api(client, name="")
    assert response.status_code == 400
    assert "name" in data["error"]


def test_create_device_requires_ip(client):
    response, data = create_device_via_api(client, ip_address="")
    assert response.status_code == 400


def test_create_device_invalid_ip(client):
    response, data = create_device_via_api(client, ip_address="999.999.1.1")
    assert response.status_code == 400
    assert "Invalid" in data["error"]


def test_create_device_rejects_ipv6(client):
    response, data = create_device_via_api(client, ip_address="2001:db8::1")
    assert response.status_code == 400


def test_create_device_invalid_type(client):
    response, data = create_device_via_api(client, device_type="refrigerator")
    assert response.status_code == 400
    assert "device type" in data["error"]


def test_create_device_invalid_interval(client):
    response, data = create_device_via_api(client, monitoring_interval=2)
    assert response.status_code == 400
    response, data = create_device_via_api(client, monitoring_interval="fast")
    assert response.status_code == 400


def test_create_device_invalid_json(client):
    response = client.post(
        "/api/devices", data="{not valid json", content_type="application/json"
    )
    assert response.status_code == 400
    assert "JSON" in response.get_json()["error"]


def test_create_device_empty_body(client):
    response = client.post("/api/devices", data="", content_type="application/json")
    assert response.status_code == 400


# --------------------------- read ---------------------------


def test_list_devices_empty(client):
    response = client.get("/api/devices")
    assert response.status_code == 200
    assert response.get_json() == []


def test_list_devices(client):
    create_device_via_api(client, name="server-a", ip_address="10.0.0.1")
    create_device_via_api(client, name="server-b", ip_address="10.0.0.2")

    response = client.get("/api/devices")
    assert response.status_code == 200
    devices = response.get_json()
    assert len(devices) == 2
    assert [d["name"] for d in devices] == ["server-a", "server-b"]


def test_get_device(client):
    _, created = create_device_via_api(client)
    response = client.get(f"/api/devices/{created['id']}")
    assert response.status_code == 200
    assert response.get_json()["name"] == "web-server"


def test_get_device_not_found(client):
    response = client.get("/api/devices/999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Device not found."


# --------------------------- update ---------------------------


def test_update_device(client):
    _, created = create_device_via_api(client)
    response = client.put(
        f"/api/devices/{created['id']}",
        json={"name": "renamed-server", "device_type": "router"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["name"] == "renamed-server"
    assert data["device_type"] == "router"
    assert data["ip_address"] == "192.168.1.10"  # untouched field stays


def test_update_device_not_found(client):
    response = client.put("/api/devices/999", json={"name": "x"})
    assert response.status_code == 404


def test_update_device_invalid_ip(client):
    _, created = create_device_via_api(client)
    response = client.put(f"/api/devices/{created['id']}", json={"ip_address": "nope!"})
    assert response.status_code == 400


# --------------------------- delete ---------------------------


def test_delete_device(client):
    _, created = create_device_via_api(client)
    response = client.delete(f"/api/devices/{created['id']}")
    assert response.status_code == 200

    response = client.get(f"/api/devices/{created['id']}")
    assert response.status_code == 404


def test_delete_device_not_found(client):
    response = client.delete("/api/devices/999")
    assert response.status_code == 404


# --------------------------- health & status ---------------------------


def test_health_endpoint(client):
    create_device_via_api(client)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["total_devices"] == 1
    assert data["monitoring_active"] is False  # disabled in tests


def test_device_status_endpoint(client):
    _, created = create_device_via_api(client)
    response = client.get(f"/api/devices/{created['id']}/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["device_id"] == created["id"]
    assert data["status"] == "UNKNOWN"
    assert data["latest_history"] is None


def test_device_status_not_found(client):
    response = client.get("/api/devices/999/status")
    assert response.status_code == 404


def test_device_history_endpoint_empty(client):
    _, created = create_device_via_api(client)
    response = client.get(f"/api/devices/{created['id']}/history")
    assert response.status_code == 200
    assert response.get_json() == []
