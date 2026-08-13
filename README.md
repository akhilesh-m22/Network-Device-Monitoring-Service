# Network Device Monitoring Service

A lightweight web application that lets you register network devices (servers, routers,
switches, workstations) and automatically monitors whether they are reachable.

A **background thread** pings every registered device every few seconds, stores the
results (UP/DOWN, response time) in SQLite, and keeps a per-device **check history**.
Everything is visible in a simple browser dashboard backed by a small REST API.

Built for a student portfolio: the whole project can be understood in 1-2 days and runs
locally on a normal laptop. No Docker, no cloud, no external services.

---

## Features

- **Device management (CRUD)** — add, list, view, update, and delete devices through
  both a web UI and a REST API.
- **Input validation** — IP addresses and hostnames are validated; invalid input is
  rejected with a clear error message.
- **Automatic monitoring** — a background thread pings all devices on a configurable
  interval and never blocks the web server.
- **Health data** — current status (UP/DOWN), response time in ms, last check time, and
  success/failure counters per device.
- **Monitoring history** — every check is recorded; the last N checks per device can be
  retrieved.
- **Web dashboard** — summary cards (total / up / down / avg response / last check) and a
  device table with add, edit, delete, and history actions. Auto-refreshes every 10 s.
- **REST API** — JSON API with proper HTTP status codes (200/201/400/404/500).
- **Tests** — pytest suite (~30 tests) with the real ping/subprocess call mocked, so
  tests run offline on any OS.
- **Cross-platform ping** — handles Windows, Linux, and macOS ping command syntax.

## Technologies

| Layer      | Technology                                    |
| ---------- | --------------------------------------------- |
| Backend    | Python 3, Flask                               |
| Database   | SQLite via SQLAlchemy (Flask-SQLAlchemy)      |
| Frontend   | HTML, CSS, vanilla JavaScript (no frameworks) |
| Background | Python `threading`                            |
| Testing    | pytest                                        |
| Versioning | Git                                           |

## Architecture

```
Browser (HTML/CSS/JS)
        |
        | HTTP + JSON
        v
Flask app (app/routes.py)
   |                    \
   | queries/writes      spawns on startup
   v                      v
SQLAlchemy models      MonitorService thread (app/monitor.py)
   |                      |
   v                      v
SQLite database        subprocess ping (app/utils.py)
```

- **Flask routes** handle browser requests and the JSON REST API.
- **Models** (`Device`, `MonitoringHistory`) map to the two SQLite tables.
- **MonitorService** is a daemon thread started by the app factory. Every cycle it loads
  all devices and pings each one; results update the `devices` row and append a
  `monitoring_history` row. A slow/unreachable device cannot block anything because
  `ping` is called with a timeout.
- **utils.py** builds a fixed ping command (no `shell=True`, user input never becomes a
  shell command) and parses the response time from the output.
- The dashboard polls the API with `fetch()` and re-renders the table.

### How monitoring works (step by step)

1. `create_app()` starts `MonitorService` as a daemon thread.
2. The thread loops: run one cycle, sleep `MONITOR_CHECK_INTERVAL` seconds, repeat.
3. One cycle = `check_all_devices()` → for each device `check_device(device)`:
   - `ping_device(ip, timeout)` runs `ping` once via `subprocess.run` with a timeout.
   - Windows: `ping -n 1 -w <ms> host` · Linux: `ping -c 1 -W <s> host` ·
     macOS: `ping -c 1 -W <ms> host`.
   - Return code 0 → UP (response time parsed from output); anything else, a
     `TimeoutExpired`, or any exception → DOWN.
   - The device row is updated (status, last_checked, response time, counters) and a
     `MonitoringHistory` row is inserted, then committed.
4. If a device is deleted mid-check, the commit fails, the session is rolled back and the
   thread keeps running.
5. All ping failures are treated as DOWN; an exception never kills the thread.

## Project structure

```
Network_Device_Monitoring_Service/
│
├── app/
│   ├── __init__.py        # app factory: creates Flask app, DB, starts monitor
│   ├── models.py          # Device and MonitoringHistory models
│   ├── routes.py          # dashboard page + REST API routes
│   ├── monitor.py         # MonitorService background thread
│   ├── utils.py           # input validation + cross-platform ping
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── style.css
│       └── app.js
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py        # fixtures: temp DB, test client, helpers
│   ├── test_api.py        # CRUD + validation + health/status tests
│   └── test_monitor.py    # ping/validation/monitor logic tests (mocked ping)
│
├── run.py                 # entry point: python run.py
├── config.py              # configuration (env-var overridable)
├── requirements.txt
├── .gitignore
└── README.md
```

## Database schema

**devices**

| Column               | Type      | Notes                                |
| -------------------- | --------- | ------------------------------------ |
| id                   | INTEGER   | primary key                          |
| name                 | TEXT      | required                             |
| ip_address           | TEXT      | required (IPv4 or hostname)          |
| device_type          | TEXT      | server / router / switch / workstation |
| description          | TEXT      | optional                             |
| monitoring_interval  | INTEGER   | seconds, min 5                       |
| created_at           | DATETIME  |                                      |
| status               | TEXT      | UP / DOWN / UNKNOWN                  |
| last_checked         | DATETIME  |                                      |
| response_time_ms     | FLOAT     |                                      |
| successful_checks    | INTEGER   |                                      |
| failed_checks        | INTEGER   |                                      |

**monitoring_history**

| Column        | Type     | Notes                                |
| ------------- | -------- | ------------------------------------ |
| id            | INTEGER  | primary key                          |
| device_id     | INTEGER  | FK → devices.id (cascade delete)     |
| status        | TEXT     | UP / DOWN                            |
| response_time | FLOAT    | ms, NULL when unreachable            |
| checked_at    | DATETIME |                                      |

The database file `network_monitor.db` is created automatically on first run (SQLite).

## API endpoints

| Method | Endpoint                      | Description                          | Status codes |
| ------ | ----------------------------- | ------------------------------------ | ------------ |
| GET    | `/`                           | Dashboard (HTML)                     | 200          |
| GET    | `/api/devices`                | List all devices                     | 200          |
| GET    | `/api/devices/<id>`           | View one device                      | 200 / 404    |
| POST   | `/api/devices`                | Add a device                         | 201 / 400    |
| PUT    | `/api/devices/<id>`           | Update a device (partial allowed)    | 200 / 400 / 404 |
| DELETE | `/api/devices/<id>`           | Delete a device and its history      | 200 / 404    |
| GET    | `/api/devices/<id>/status`    | Current health of a device           | 200 / 404    |
| GET    | `/api/devices/<id>/history`   | Recent checks (default 20, `?limit=`) | 200 / 400 / 404 |
| GET    | `/api/health`                 | Service health + summary counts      | 200          |

All errors are JSON, e.g. `{"error": "Device not found."}`.

## Install & run

Requirements: Python 3.9+ (developed on 3.11).

```bash
# 1. Clone (or copy) the project
git clone <your-repo-url>
cd Network_Device_Monitoring_Service

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python run.py
```

Open http://127.0.0.1:5000 in your browser.

> Tip: register a device with `127.0.0.1` (your own machine) to see a device go UP
> immediately, and `192.0.2.1` (TEST-NET, always unreachable) to see a DOWN one.

### Configuration (optional, via environment variables)

| Variable                  | Default      | Meaning                     |
| ------------------------- | ------------ | --------------------------- |
| `DATABASE_URL`            | sqlite:///…  | SQLAlchemy DB URI           |
| `MONITOR_CHECK_INTERVAL`  | 10           | seconds between cycles      |
| `PING_TIMEOUT_SECONDS`    | 3            | per-device ping timeout     |
| `SECRET_KEY`              | dev value    | Flask session key           |

## Running tests

```bash
pip install -r requirements.txt   # includes pytest
python -m pytest tests -v
```

The suite uses a fresh temporary SQLite database per test and mocks
`app.monitor.ping_device` / `subprocess.run`, so it needs **no network access**.

## Example API requests

```bash
# Add a device
curl -X POST http://127.0.0.1:5000/api/devices \
  -H "Content-Type: application/json" \
  -d '{"name":"web-server","ip_address":"127.0.0.1","device_type":"server","description":"main web server","monitoring_interval":60}'

# List devices
curl http://127.0.0.1:5000/api/devices

# Get one device
curl http://127.0.0.1:5000/api/devices/1

# Update a device
curl -X PUT http://127.0.0.1:5000/api/devices/1 \
  -H "Content-Type: application/json" \
  -d '{"name":"renamed-server"}'

# Delete a device
curl -X DELETE http://127.0.0.1:5000/api/devices/1

# Device status
curl http://127.0.0.1:5000/api/devices/1/status

# Monitoring history (last 20 checks)
curl http://127.0.0.1:5000/api/devices/1/history

# Health
curl http://127.0.0.1:5000/api/health
```

## Screenshots

*Add screenshots here (dashboard with UP/DOWN badges, history modal).*

## Security notes

- All database access goes through the SQLAlchemy ORM — no raw SQL, no SQL injection.
- `ping` is called via `subprocess.run` with a **fixed argument list** and `shell=False`;
  user input can never be executed as a command.
- API input is validated (IP/hostname format, allowed types, value ranges).
- No passwords or secrets are stored. The database only holds device metadata and
  monitoring results.

## Possible future improvements

- Per-device check scheduling using each device's `monitoring_interval` (currently all
  devices are checked every cycle).
- Alerting (email/webhook) when a device goes DOWN.
- Authentication and user accounts.
- ICMP-less checks for hosts that block ping (TCP port checks).
- Pagination for history endpoints.
- Charts for response-time trends (e.g. Chart.js).
- Data retention/cleanup for old history records.
- Deploy behind a real WSGI server (gunicorn/waitress) instead of Flask dev server.
