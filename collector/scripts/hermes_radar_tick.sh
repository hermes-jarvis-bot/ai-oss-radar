#!/usr/bin/env bash
# Hermes scheduled protocol adapter. stdout contains only the final report;
# stderr is retained as scheduler telemetry and is never delivered verbatim.
set -euo pipefail
cd "$(dirname "$0")/.."
exec flock -n /tmp/ai-oss-radar.tick.lock docker compose run --rm radar
