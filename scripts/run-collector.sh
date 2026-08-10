#!/usr/bin/env bash
# stdout is the operator-facing report; operational telemetry remains on stderr.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec flock -n /tmp/ai-oss-radar.tick.lock docker compose --env-file "$ROOT/deploy/.env" -f "$ROOT/deploy/docker-compose.collector.yml" run --rm collector
