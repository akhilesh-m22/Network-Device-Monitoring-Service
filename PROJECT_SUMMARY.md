# Network Device Monitoring Service — Project Summary

## A. Project structure

```
Network_Device_Monitoring_Service/
├── app/
│   ├── __init__.py        # app factory: creates Flask app, DB tables, starts monitor
│   ├── models.py          # Device + MonitoringHistory models (SQLAlchemy)
│   ├── routes.py          # dashboard page + full REST API + JSON error handlers
│   ├── monitor.py         # MonitorService background thread
│   ├── utils.py           # IP/hostname validation + cross-platform ping
│   ├── templates/dashboard.html
│   └── static/style.css, app.js
├── tests/
│   ├── __init__.py, conftest.py (fixtures)
│   ├── test_api.py        # 23 tests — CRUD, validation, health/status
│   └── test_monitor.py    # 17 tests — ping (mocked), monitor logic, thread
├── run.py                 # entry point
├── config.py              # env-var-overridable configuration
├── requirements.txt, .gitignore, README.md
```

## B. Source code

All code is in the files above (17 files, ~1500 lines). Key design decisions: app-factory pattern (`create_app`), model `to_dict()` for JSON, monitor thread started by the factory with a `START_MONITORING=False` escape hatch for tests, and `ping` called with a fixed argument list (`shell=False` — no command injection).

## C. Setup commands

```bash
git clone <your-repo-url>
cd Network_Device_Monitoring_Service
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
```

## D. Run commands

```bash
python run.py                   # → http://127.0.0.1:5000
```

## E. Test commands

```bash
python -m pytest tests -v       # 40 tests, offline (ping mocked)
```

## F. API endpoint documentation

| Method | Endpoint | Result |
|---|---|---|
| GET | `/` | dashboard HTML |
| GET | `/api/devices` | `200` list |
| GET | `/api/devices/<id>` | `200` / `404` |
| POST | `/api/devices` | `201` / `400` |
| PUT | `/api/devices/<id>` | `200` / `400` / `404` (partial update) |
| DELETE | `/api/devices/<id>` | `200` / `404` |
| GET | `/api/devices/<id>/status` | `200` / `404` |
| GET | `/api/devices/<id>/history?limit=20` | `200` / `400` / `404` |
| GET | `/api/health` | `200` counts + monitor alive |

All errors are returned as JSON, e.g. `{"error": "Device not found."}`.

Example requests:

```bash
# Add a device
curl -X POST http://127.0.0.1:5000/api/devices \
  -H "Content-Type: application/json" \
  -d '{"name":"web-server","ip_address":"127.0.0.1","device_type":"server","monitoring_interval":60}'

# List / get / update / delete
curl http://127.0.0.1:5000/api/devices
curl http://127.0.0.1:5000/api/devices/1
curl -X PUT http://127.0.0.1:5000/api/devices/1 -H "Content-Type: application/json" -d '{"name":"renamed"}'
curl -X DELETE http://127.0.0.1:5000/api/devices/1

# Status, history, health
curl http://127.0.0.1:5000/api/devices/1/status
curl http://127.0.0.1:5000/api/devices/1/history
curl http://127.0.0.1:5000/api/health
```

## G. How each major component works

- **`utils.py`** — `validate_ip_or_hostname()` uses `ipaddress` + hostname regex (rejects IPv6, out-of-range octets like `999.999.1.1`, and garbage). `ping_device()` builds an OS-specific fixed command (Windows `-n 1 -w <ms>`, Linux `-c 1 -W <s>`, macOS ms), runs it via `subprocess.run` with a timeout, parses `time=Xms` from output.
- **`monitor.py`** — daemon `threading.Thread`. Loops: `check_all_devices()` → for each device `check_device()` (ping with 3s timeout → set UP/DOWN, counters, insert history row, commit). Exceptions are swallowed per-device so one broken device can't kill the thread. SQLAlchemy session rolls back if a device is deleted mid-check.
- **`routes.py`** — blueprint with a shared `_validate_payload()` used by POST and PUT, `_read_json_body()` for malformed JSON → `400`, JSON error handlers, ORM-only queries (no raw SQL).
- **`app/__init__.py`** — factory pattern: `db.init_app`, register routes, `db.create_all()` (auto-creates SQLite file), start monitor.
- **Frontend** — vanilla JS `fetch()` polling `/api/devices` every 10s, renders stats + table, modal for add/edit, confirm for delete, history modal.

## H. Interview questions (prepare these)

1. How does the monitor thread work, and why is it a daemon thread?
2. What happens if a device is deleted while the monitor is checking it?
3. Why do the monitor and Flask need an "application context"? What would happen without it?
4. How do you prevent a slow/unreachable device from blocking monitoring? (timeout)
5. How does `subprocess` usage here prevent command injection? (fixed arg list, `shell=False`)
6. Why did you validate IPs with `ipaddress` AND a regex? What edge cases does each catch?
7. Why SQLite? Why SQLAlchemy instead of raw SQL? (ORM prevents injection, relationships, portability)
8. How does cascade delete work for a device's history?
9. How do the tests run without network access? (monkeypatching `ping_device`/`subprocess.run`)
10. Why does each test get its own temporary database?
11. What HTTP status codes do you return and why (201 vs 200, 400 vs 404)?
12. How do you know the background thread is running? (`/api/health` → `monitoring_active`)
13. How would you scale this to thousands of devices? (thread pool / per-device scheduling)
14. What is the difference between `app.config` and `os.environ` configuration here?
15. What would you improve next? (per-device intervals, alerts, auth — all listed in README "Future improvements")

## I. Resume description (3-4 lines, only implemented features)

> Built a Flask + SQLite network monitoring web app that registers devices via a REST API and uses a background Python thread to ping them on a schedule, persisting UP/DOWN status, response times, and check history. Implemented CRUD endpoints with input validation, a vanilla JS dashboard with live auto-refresh, and a 40-test pytest suite with mocked subprocess calls that runs offline. Followed a clean app-factory architecture, used SQLAlchemy ORM throughout, and managed the project with Git.
