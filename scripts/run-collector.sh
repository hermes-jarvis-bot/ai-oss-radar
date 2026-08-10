#!/usr/bin/env bash
# stdout is the operator-facing report; operational telemetry remains on stderr.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RADAR_ENV_FILE:-$ROOT/deploy/.env}"
exec flock -n /tmp/ai-oss-radar.tick.lock docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.collector.yml" run --rm collector
