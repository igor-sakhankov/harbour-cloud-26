#!/usr/bin/env bash
# Start the StarHarbour server locally (no Docker/Toxiproxy required).
export JAVA_HOME=/opt/homebrew/opt/openjdk
export PATH="$JAVA_HOME/bin:$PATH"
SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun
