#!/usr/bin/env bash
set -euo pipefail
bind="${DASHBOARD_BIND:-127.0.0.1:8096}"
curl -fsS "http://${bind}/health"
