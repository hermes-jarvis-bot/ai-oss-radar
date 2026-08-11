#!/usr/bin/env python3
"""Private-network, token-protected runner for one AI OSS Radar collection."""
from __future__ import annotations

import hmac
import json
import os
import socket
import subprocess
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("RADAR_ROOT", "/root/projects/ai-oss-radar"))
RUNNER_TOKEN = os.environ["RADAR_REFRESH_TOKEN"]
ENV_FILE = os.environ.get("RADAR_ENV_FILE", str(ROOT / "deploy/.env.production"))
LOG_DIR = Path(os.environ.get("RADAR_REFRESH_LOG_DIR", "/root/var/ai-oss-radar/refresh-runs"))
LOG_RETENTION = int(os.environ.get("RADAR_REFRESH_LOG_RETENTION", "50"))
SCRIPT = ROOT / "scripts/run-collector.sh"
BIND_HOST = os.environ.get("RADAR_REFRESH_BIND", "127.0.0.1")
LOCK = threading.Lock()
STATE: dict[str, object] = {"state": "idle", "run_id": None}


def payload(handler: BaseHTTPRequestHandler, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def authorised(handler: BaseHTTPRequestHandler) -> bool:
    supplied = handler.headers.get("X-Radar-Refresh-Token", "")
    return hmac.compare_digest(supplied, RUNNER_TOKEN)


def prune_logs() -> None:
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    for log_path in logs[max(LOG_RETENTION, 0) :]:
        log_path.unlink(missing_ok=True)


def run_collection(run_id: str) -> None:
    log_path = LOG_DIR / f"{run_id}.log"
    environment = os.environ.copy()
    environment["RADAR_ENV_FILE"] = ENV_FILE
    try:
        with log_path.open("wb") as log:
            result = subprocess.run([str(SCRIPT)], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
        with LOCK:
            STATE.update({"state": "succeeded" if result.returncode == 0 else "failed", "exit_code": result.returncode, "log": str(log_path)})
    except Exception:
        with LOCK:
            STATE.update({"state": "failed", "exit_code": None})
    finally:
        prune_logs()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            payload(self, HTTPStatus.OK, {"ok": True})
            return
        if self.path == "/status":
            if not authorised(self):
                payload(self, HTTPStatus.UNAUTHORIZED, {"detail": "Unauthorized"})
                return
            with LOCK:
                payload(self, HTTPStatus.OK, {key: value for key, value in STATE.items() if key != "log"})
            return
        payload(self, HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/run":
            payload(self, HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        if not authorised(self):
            payload(self, HTTPStatus.UNAUTHORIZED, {"detail": "Unauthorized"})
            return
        with LOCK:
            if STATE["state"] == "running":
                payload(self, HTTPStatus.CONFLICT, {"detail": "Collection already running", "run_id": STATE["run_id"]})
                return
            run_id = uuid.uuid4().hex
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(LOG_DIR, 0o700)
            STATE.clear()
            STATE.update({"state": "running", "run_id": run_id})
            threading.Thread(target=run_collection, args=(run_id,), daemon=True).start()
        payload(self, HTTPStatus.ACCEPTED, {"run_id": run_id, "state": "running"})


class RunnerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        request, address = super().get_request()
        request.settimeout(5)
        return request, address


if __name__ == "__main__":
    RunnerHTTPServer((BIND_HOST, 8097), Handler).serve_forever()
