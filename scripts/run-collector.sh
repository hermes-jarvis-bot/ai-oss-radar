#!/usr/bin/env bash
# stdout is the operator-facing report; Compose/build telemetry remains internal.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${RADAR_ENV_FILE:-$ROOT/deploy/.env}"
output=$(mktemp)
trap 'rm -f "$output"' EXIT

if ! flock -n /tmp/ai-oss-radar.tick.lock \
  docker compose --env-file "$ENV_FILE" -f "$ROOT/deploy/docker-compose.collector.yml" run --rm --build collector >"$output"; then
  cat "$output" >&2
  exit 1
fi

# Hermes delivers stdout verbatim. Emit only the collector report, not Docker
# build stages or scheduler-owned telemetry preceding it.
awk '
  /^AI OSS Radar — [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC$/ { report=1 }
  report { print }
' "$output"
