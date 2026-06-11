# Load Balancer — StarHarbour Payments API

A redirect load balancer that distributes traffic across multiple instances
of the StarHarbour Payments API using HTTP 302 redirects and round-robin scheduling.

## Files

| File | Purpose |
|---|---|
| `load_balancer.py` | Main load balancer server |
| `config.json` | List of backend server URLs |
| `test_load_balancer.py` | Automated tests (no live server needed) |

## Design Decisions

### 1. HTTP 302 Redirect (not proxying)
Instead of forwarding the request itself, the load balancer responds with
`302 Found` and a `Location` header pointing to a backend. The client
then talks directly to that backend. This is simpler and uses less memory
since the load balancer never touches the request/response body.

### 2. How the instance list works
Backend URLs are stored in `config.json`:
```json
{
  "servers": [
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:8082"
  ]
}
```
Edit this file to add or remove instances. No code changes needed.

### 3. Health checks
Before every redirect, the load balancer pings the candidate backend with:
```
GET /api/v1/payments?storeId=health-check
```
- Any 2xx or 4xx response = server is alive ✅
- 5xx or connection error = server is dead ❌ (skipped, try next)

If all backends are down, the load balancer returns `503 Service Unavailable`.

### 4. Round-robin algorithm
Requests are distributed in order: server 1 → server 2 → server 3 → server 1 → ...
Dead servers are skipped automatically and the cycle continues with the rest.
Thread-safe (multiple requests handled concurrently).

## How to run

### Requirements
- Python 3.8+ (no third-party packages needed)
- At least one StarHarbour Payments API instance running

### Start the load balancer
```bash
cd submissions/load-balancer
python load_balancer.py
```

Load balancer runs on **http://localhost:8000** by default.

### Point your CSV uploader at the load balancer
```bash
cd submissions/csv-uploader
python uploader.py --url http://localhost:8000
```

### Run tests (no server needed)
```bash
python -m pytest test_load_balancer.py -v
```

## How to simulate multiple backends (Windows)

Open 3 separate Command Prompt windows and run each on a different port:
```bash
# Window 1
set SERVER_PORT=8080 && ./gradlew bootRun

# Window 2 — needs a copy of the app or different port config
# (for demo purposes, the load balancer will skip unreachable ones)
```
