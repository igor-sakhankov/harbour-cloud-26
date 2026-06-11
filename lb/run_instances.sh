#!/usr/bin/env bash
#
# Launch 3 instances of the StarHarbour Payments app + the redirect load balancer.
#
#   instance 1 -> http://localhost:8081
#   instance 2 -> http://localhost:8082
#   instance 3 -> http://localhost:8083
#   load balancer -> http://localhost:8080   (redirects to the instances)
#
# Docker Compose / Toxiproxy is disabled so the three instances don't fight over
# the shared 9091/8474 ports. Ctrl-C tears everything down.
#
# Usage:
#   ./lb/run_instances.sh            # build jar if needed, then run everything
#   SKIP_BUILD=1 ./lb/run_instances.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$REPO_ROOT/build/libs/cloud-0.0.1-SNAPSHOT.jar"
PORTS=(8081 8082 8083)
PIDS=()

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

if [[ "${SKIP_BUILD:-0}" != "1" || ! -f "$JAR" ]]; then
  echo "Building jar..."
  (cd "$REPO_ROOT" && ./gradlew bootJar -q)
fi

echo "Starting 3 app instances..."
for port in "${PORTS[@]}"; do
  java -jar "$JAR" \
    --server.port="$port" \
    --spring.docker.compose.enabled=false \
    > "/tmp/app-$port.log" 2>&1 &
  PIDS+=($!)
  echo "  instance on :$port  (logs: /tmp/app-$port.log)"
done

echo "Waiting for instances to come up..."
for port in "${PORTS[@]}"; do
  for _ in $(seq 1 30); do
    if curl -s -o /dev/null "http://127.0.0.1:$port/"; then break; fi
    sleep 1
  done
done

echo "Starting load balancer on :8080..."
LB_BACKENDS="http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083" \
  python3 "$REPO_ROOT/lb/load_balancer.py" --config "$REPO_ROOT/lb/config.json" \
  > /tmp/lb.log 2>&1 &
PIDS+=($!)
sleep 1

cat <<EOF

Everything is up:
  load balancer : http://localhost:8080
  instances     : http://localhost:8081, :8082, :8083

Now run the demo client in another terminal:
  python3 lb/demo_client.py

Press Ctrl-C here to stop all instances and the load balancer.
EOF

wait
