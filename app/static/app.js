// Frontend logic for the Network Device Monitoring dashboard.
// Plain JavaScript: fetch() to call the REST API and re-render the page.

const API_URL = "/api/devices";

// ----------------------- helpers -----------------------

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = "toast" + (isError ? " error" : "");
    setTimeout(() => toast.classList.add("hidden"), 3000);
}

function statusBadge(status) {
    const safe = status || "UNKNOWN";
    return `<span class="badge ${escapeHtml(safe)}">${escapeHtml(safe)}</span>`;
}

function formatTime(value) {
    return value ? escapeHtml(value) : "-";
}

function formatResponse(ms) {
    return ms == null ? "-" : escapeHtml(ms) + " ms";
}

// ----------------------- data loading -----------------------

async function loadDevices() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error("Failed to load devices");
        const devices = await response.json();
        renderStats(devices);
        renderTable(devices);
    } catch (err) {
        document.getElementById("device-tbody").innerHTML =
            '<tr><td colspan="7" class="empty-row">Could not load devices: ' +
            escapeHtml(err.message) + "</td></tr>";
    }
}

function renderStats(devices) {
    const total = devices.length;
    const up = devices.filter((d) => d.status === "UP").length;
    const down = devices.filter((d) => d.status === "DOWN").length;
    const withResponse = devices.filter((d) => d.response_time_ms != null);
    const avg = withResponse.length
        ? (withResponse.reduce((sum, d) => sum + d.response_time_ms, 0) / withResponse.length).toFixed(1) + " ms"
        : "-";
    const lastChecked = devices
        .map((d) => d.last_checked)
        .filter(Boolean)
        .sort()
        .reverse()[0];

    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-up").textContent = up;
    document.getElementById("stat-down").textContent = down;
    document.getElementById("stat-avg").textContent = avg;
    document.getElementById("stat-last").textContent = lastChecked || "-";
}

function renderTable(devices) {
    const tbody = document.getElementById("device-tbody");
    if (devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No devices yet. Click "+ Add Device".</td></tr>';
        return;
    }

    tbody.innerHTML = devices
        .map(
            (d) => `
        <tr>
            <td>${escapeHtml(d.name)}</td>
            <td>${escapeHtml(d.ip_address)}</td>
            <td>${escapeHtml(d.device_type)}</td>
            <td>${statusBadge(d.status)}</td>
            <td>${formatResponse(d.response_time_ms)}</td>
            <td>${formatTime(d.last_checked)}</td>
            <td>
                <div class="action-row">
                    <button class="btn btn-small btn-secondary" onclick="openEditModal(${d.id})">Edit</button>
                    <button class="btn btn-small btn-danger" onclick="deleteDevice(${d.id})">Delete</button>
                    <button class="btn btn-small btn-secondary" onclick="showHistory(${d.id})">History</button>
                </div>
            </td>
        </tr>`
        )
        .join("");
}

// ----------------------- add / edit -----------------------

function openAddModal() {
    document.getElementById("device-form").reset();
    document.getElementById("device-id").value = "";
    document.getElementById("modal-title").textContent = "Add Device";
    document.getElementById("form-error").classList.add("hidden");
    document.getElementById("modal").classList.remove("hidden");
}

async function openEditModal(deviceId) {
    try {
        const response = await fetch(`${API_URL}/${deviceId}`);
        if (!response.ok) throw new Error("Device not found");
        const device = await response.json();

        document.getElementById("device-id").value = device.id;
        document.getElementById("name").value = device.name;
        document.getElementById("ip_address").value = device.ip_address;
        document.getElementById("device_type").value = device.device_type;
        document.getElementById("monitoring_interval").value = device.monitoring_interval;
        document.getElementById("description").value = device.description || "";
        document.getElementById("modal-title").textContent = "Edit Device";
        document.getElementById("form-error").classList.add("hidden");
        document.getElementById("modal").classList.remove("hidden");
    } catch (err) {
        showToast(err.message, true);
    }
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}

async function saveDevice(event) {
    event.preventDefault();

    const id = document.getElementById("device-id").value;
    const payload = {
        name: document.getElementById("name").value.trim(),
        ip_address: document.getElementById("ip_address").value.trim(),
        device_type: document.getElementById("device_type").value,
        monitoring_interval: parseInt(document.getElementById("monitoring_interval").value, 10),
        description: document.getElementById("description").value.trim(),
    };

    const url = id ? `${API_URL}/${id}` : API_URL;
    const method = id ? "PUT" : "POST";

    try {
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Request failed");
        }
        closeModal();
        showToast(id ? "Device updated" : "Device added");
        loadDevices();
    } catch (err) {
        const errorBox = document.getElementById("form-error");
        errorBox.textContent = err.message;
        errorBox.classList.remove("hidden");
    }
}

// ----------------------- delete -----------------------

async function deleteDevice(deviceId) {
    if (!confirm("Delete this device and its monitoring history?")) return;
    try {
        const response = await fetch(`${API_URL}/${deviceId}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Delete failed");
        showToast("Device deleted");
        loadDevices();
    } catch (err) {
        showToast(err.message, true);
    }
}

// ----------------------- history -----------------------

async function showHistory(deviceId) {
    try {
        const response = await fetch(`${API_URL}/${deviceId}/history?limit=20`);
        const records = await response.json();
        if (!response.ok) throw new Error(records.error || "Failed to load history");

        const deviceResponse = await fetch(`${API_URL}/${deviceId}`);
        const device = await deviceResponse.json();
        document.getElementById("history-title").textContent = `History — ${device.name}`;

        const tbody = document.getElementById("history-tbody");
        if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-row">No history yet. The monitor checks devices every few seconds.</td></tr>';
        } else {
            tbody.innerHTML = records
                .map(
                    (r) => `
                <tr>
                    <td>${formatTime(r.checked_at)}</td>
                    <td>${statusBadge(r.status)}</td>
                    <td>${formatResponse(r.response_time)}</td>
                </tr>`
                )
                .join("");
        }
        document.getElementById("history-modal").classList.remove("hidden");
    } catch (err) {
        showToast(err.message, true);
    }
}

function closeHistoryModal() {
    document.getElementById("history-modal").classList.add("hidden");
}

// ----------------------- wire up -----------------------

document.getElementById("btn-add").addEventListener("click", openAddModal);
document.getElementById("btn-cancel").addEventListener("click", closeModal);
document.getElementById("btn-close-history").addEventListener("click", closeHistoryModal);
document.getElementById("btn-refresh").addEventListener("click", loadDevices);
document.getElementById("device-form").addEventListener("submit", saveDevice);

// Close modals when clicking on the dimmed background.
document.getElementById("modal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
});
document.getElementById("history-modal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeHistoryModal();
});

// Initial load, then refresh every 10 seconds so the dashboard shows
// live monitoring results from the background thread.
loadDevices();
setInterval(loadDevices, 10000);
