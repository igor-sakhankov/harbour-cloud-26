#!/usr/bin/env bash
# Build the payments app once and start N instances on consecutive ports,
# so the load balancer has something real to spread traffic across.
#
#   ./run_instances.sh [N] [BASE_PORT]
#   ./run_instances.sh 3 8081
#
# Stop them again with:  kill $(cat /tmp/lb-instances/pids)
set -euo pipefail

N="${1:-3}"
BASE_PORT="${2:-8081}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK=/tmp/lb-instances
mkdir -p "$WORK"

echo "Building payments app jar..."
(cd "$REPO_ROOT" && ./gradlew -q bootJar)
JAR="$(ls "$REPO_ROOT"/build/libs/*.jar | head -1)"

: > "$WORK/pids"
for i in $(seq 0 $((N - 1))); do
  port=$((BASE_PORT + i))
  SPRING_DOCKER_COMPOSE_ENABLED=false java -jar "$JAR" --server.port="$port" \
    > "$WORK/instance-$port.log" 2>&1 &
  echo "$!" >> "$WORK/pids"
  echo "instance up on http://localhost:$port (pid $!)"
done

echo
echo "Started $N instances. Logs: $WORK/instance-*.log"
echo "Stop them with: kill \$(cat $WORK/pids)"
