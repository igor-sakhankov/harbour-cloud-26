# Load Balancer — StarHarbour Payments API

A Python-based redirect load balancer that distributes traffic across multiple StarHarbour backend instances using:

* HTTP 302 redirects
* Round Robin scheduling
* Health checks

Instead of proxying traffic, the load balancer tells each client which backend to talk to. After the redirect, the client communicates with the selected instance directly.

---

## Files

| File               | Purpose                           |
| ------------------ | --------------------------------- |
| `load_balancer.py` | Main load balancer server         |
| `instances.json`   | Backend instance configuration    |
| `client_test.py`   | Demonstrates Round Robin behavior |
| `requirements.txt` | Python dependencies               |

---

## Design Decisions

### 1. HTTP 302 Redirect (not proxying)

The load balancer does **not** forward requests or request bodies to the backends. Instead, it responds with an HTTP 302 status and a `Location` header pointing at the selected instance. The client then repeats its request directly against that backend.

```http
GET /api/v1/payments HTTP/1.1
Host: localhost:8000

HTTP/1.1 302 Found
Location: http://localhost:8081/api/v1/payments
```

The original path and query parameters are preserved in the `Location` header. This keeps the load balancer simple and stateless — it never touches payloads — and matches the assignment requirements.

### 2. How the instance list works

Backend instances are stored in `instances.json`, next to the load balancer script:

```json
{
  "instances": [
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:8082"
  ]
}
```

The file is loaded once at startup. No instance URLs are hardcoded in the Python code, so instances can be added or removed by editing only this file and restarting the load balancer.

### 3. Health Checks

Before redirecting a request, the load balancer verifies that the selected instance is alive. Each health check is a real request against the payments API:

```http
GET /api/v1/payments?storeId=health-check
```

with a 2-second timeout. The rules are:

* **2xx** = healthy
* **4xx** = healthy (the instance is up and processing requests, even if it rejects this particular one)
* **5xx** = unhealthy
* **Timeout / connection error** = unhealthy

Unhealthy instances are skipped automatically and the next instance in the rotation is tried. If every instance fails its health check, the load balancer responds with:

```http
503 Service Unavailable
```

### 4. Round Robin Algorithm

Requests are distributed evenly by cycling through the instance list with a shared index:

```text
Request 1 -> Instance 1
Request 2 -> Instance 2
Request 3 -> Instance 3
Request 4 -> Instance 1
```

Dead instances are skipped automatically: if the chosen instance fails its health check, the algorithm simply advances to the next one, trying each instance at most once per request.

The implementation is **thread-safe**. Flask handles requests on multiple threads, so the rotation index is protected by a `threading.Lock` — two concurrent requests can never read the same index.

---

## How to Run

### Requirements

* Python 3.11+
* Flask
* Requests
* One or more running StarHarbour backend instances

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start the Load Balancer

```bash
cd load_balancer
python load_balancer.py
```

The load balancer listens on:

```text
http://localhost:8000
```

Any request sent to this address is redirected to one of the configured backend instances.

### Start Multiple Backend Instances

Run several copies of the same StarHarbour application on different ports (macOS/Linux):

```bash
# Terminal 1
./gradlew bootRun

# Terminal 2
SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun --args='--server.port=8081'

# Terminal 3
SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun --args='--server.port=8082'
```

These are three independent instances of the same application. The first one starts the Toxiproxy sidecar via Docker Compose; the additional instances disable it to avoid port conflicts.

### Run the Client Demonstration

```bash
cd load_balancer
python client_test.py
```

The script sends 20 requests to the load balancer with `allow_redirects=False` and prints the redirect destination of each response:

```text
Request #1 -> Status: 302 -> Redirected to: http://localhost:8080/api/v1/payments
Request #2 -> Status: 302 -> Redirected to: http://localhost:8081/api/v1/payments
Request #3 -> Status: 302 -> Redirected to: http://localhost:8082/api/v1/payments
Request #4 -> Status: 302 -> Redirected to: http://localhost:8080/api/v1/payments
```

The output makes the Round Robin distribution directly visible.

### Demonstrating Fault Tolerance

1. Start three backend instances.
2. Run `client_test.py` — redirects cycle through all three instances.
3. Stop one backend instance (e.g. Ctrl+C in its terminal).
4. Run `client_test.py` again.

The stopped instance disappears from the rotation: the load balancer logs a failed health check, skips it, and the remaining instances continue serving requests. Once the instance is restarted, it rejoins the rotation automatically.

---

## Assignment Concepts Demonstrated

* Service Discovery (`instances.json`)
* Health Checking
* HTTP 302 Redirects
* Round Robin Load Balancing
* High Availability
* Fault Tolerance
