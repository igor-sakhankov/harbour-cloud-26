#!/usr/bin/env bash
# Boots 3 local instances of the harbour-cloud-26 app + the load balancer.
# Needs the app jar built:  (cd ../harbour-cloud-26 && ./gradlew bootJar)
set -euo pipefail

# Locate the app jar whether this folder lives inside the repo (../build) or
# beside it (../harbour-cloud-26/build).
JAR=$(ls ../build/libs/cloud-*-SNAPSHOT.jar ../harbour-cloud-26/build/libs/cloud-*-SNAPSHOT.jar 2>/dev/null | head -1)
if [ -z "$JAR" ]; then
  echo "App jar not found. Build it first: ./gradlew bootJar (in the harbour-cloud-26 app)."
  exit 1
fi

pids=()
for port in 8081 8082 8083; do
  java -jar "$JAR" --server.port="$port" >"/tmp/backend-$port.log" 2>&1 &
  pids+=("$!")
  echo "backend starting on :$port"
done
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT

export LB_BACKENDS=http://localhost:8081,http://localhost:8082,http://localhost:8083
export PORT=8080
echo "starting load balancer on :8080 (Ctrl-C to stop everything) ..."
pnpm start
