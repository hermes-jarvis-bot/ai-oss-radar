from __future__ import annotations

import fcntl
import hmac
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.getenv("RADAR_DB", "/data/radar.db")
CONTROL_PATH = Path(os.getenv("MANUAL_WATCHLIST", "/control/pins.json"))
REFRESH_TOKEN = os.getenv("RADAR_REFRESH_TOKEN", "")
REFRESH_RUNNER_URL = os.getenv("RADAR_REFRESH_RUNNER_URL", "http://host.docker.internal:8097")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AI OSS Radar Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class PinRequest(BaseModel):
    full_name: str


def manual_pins() -> list[str]:
    if not CONTROL_PATH.exists():
        return []
    try:
        data = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("repositories", []) if isinstance(data, dict) else []
    return sorted(
        {
            value.lower()
            for value in values
            if isinstance(value, str) and REPOSITORY_NAME.fullmatch(value)
        }
    )


@contextmanager
def manual_pins_lock() -> Any:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = CONTROL_PATH.with_suffix(".lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def save_manual_pins(values: list[str]) -> None:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=CONTROL_PATH.parent, prefix=f".{CONTROL_PATH.name}.", delete=False, encoding="utf-8"
    ) as temporary:
        temporary.write(json.dumps({"repositories": sorted(set(values))}, indent=2) + "\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    os.replace(temporary.name, CONTROL_PATH)


def db() -> sqlite3.Connection:
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Radar database is not available")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with db() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def latest_report_top() -> list[dict[str, Any]]:
    reports = Path(DB_PATH).parent / "reports"
    files = sorted(reports.glob("*.json")) if reports.exists() else []
    if not files:
        return []
    try:
        return json.loads(files[-1].read_text(encoding="utf-8")).get("top", [])
    except (OSError, json.JSONDecodeError):
        return []


@app.get("/health")
def health() -> dict[str, Any]:
    with db() as conn:
        snapshot_count = conn.execute("SELECT count(*) FROM snapshots").fetchone()[0]
        latest = conn.execute("SELECT max(ts) FROM snapshots").fetchone()[0]
    return {"ok": True, "snapshots": snapshot_count, "latest_snapshot": latest}


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    with db() as conn:
        latest = conn.execute("SELECT max(ts) FROM snapshots").fetchone()[0]
        if not latest:
            return {"latest_snapshot": None, "repositories": []}
        latest_repos = [
            dict(row)
            for row in conn.execute(
                """SELECT full_name, html_url, description, stars, language, topics, created_at, pushed_at
                   FROM snapshots WHERE ts=? ORDER BY stars DESC LIMIT 100""",
                (latest,),
            )
        ]
        metadata = {repo["full_name"]: repo for repo in latest_repos}
        repos = latest_report_top() or latest_repos
        for repo in repos:
            name = repo.get("repo") or repo["full_name"]
            repo["repo"] = name
            repo.update(metadata.get(name, {}))
            repo["full_name"] = name
            previous = conn.execute(
                """SELECT stars FROM snapshots WHERE full_name=? AND ts<?
                   ORDER BY ts DESC LIMIT 1""",
                (repo["full_name"], latest),
            ).fetchone()
            repo["delta_since_previous"] = repo["stars"] - previous[0] if previous else None
        return {"latest_snapshot": latest, "repositories": repos}


@app.get("/api/repositories")
def repositories(limit: int = 100) -> list[dict[str, Any]]:
    return rows(
        """WITH ordered AS (
               SELECT full_name, stars, ts,
                      count(*) OVER (PARTITION BY full_name) AS observations,
                      min(ts) OVER (PARTITION BY full_name) AS first_seen,
                      row_number() OVER (PARTITION BY full_name ORDER BY ts DESC) AS row_number
               FROM snapshots
           )
           SELECT full_name, stars AS current_stars, observations, first_seen, ts AS last_seen
           FROM ordered WHERE row_number=1 ORDER BY last_seen DESC, current_stars DESC LIMIT ?""",
        (min(max(limit, 1), 500),),
    )


@app.get("/api/repositories/{full_name:path}/history")
def history(full_name: str) -> dict[str, Any]:
    data = rows(
        """SELECT ts, stars, forks, pushed_at FROM snapshots WHERE lower(full_name)=lower(?)
           ORDER BY ts""",
        (full_name,),
    )
    if not data:
        raise HTTPException(status_code=404, detail="Repository was not observed")
    summary = rows(
        """SELECT full_name, html_url, description, stars, language, topics, ts
           FROM snapshots WHERE lower(full_name)=lower(?) ORDER BY ts DESC LIMIT 1""",
        (full_name,),
    )[0]
    return {"repository": full_name, "summary": summary, "history": data}


@app.get("/api/watchlist")
def watchlist() -> list[dict[str, Any]]:
    try:
        entries = rows(
            """SELECT w.full_name, w.added_at, w.expires_at, w.reason, w.pinned, w.last_seen_at,
                      s.stars, s.html_url, s.description
               FROM watchlist_candidates AS w
               LEFT JOIN snapshots AS s ON s.full_name=w.full_name
                 AND s.ts=(SELECT max(ts) FROM snapshots WHERE full_name=w.full_name)
               ORDER BY w.pinned DESC, w.expires_at DESC"""
        )
    except sqlite3.OperationalError:
        entries = []
    existing = {entry["full_name"].lower() for entry in entries}
    missing = [name for name in manual_pins() if name.lower() not in existing]
    snapshots: dict[str, dict[str, Any]] = {}
    if missing:
        placeholders = ",".join("?" for _ in missing)
        snapshot_rows = rows(
            f"""SELECT s.full_name, s.stars, s.html_url, s.description FROM snapshots AS s
                WHERE lower(s.full_name) IN ({placeholders})
                  AND s.ts=(SELECT max(ts) FROM snapshots WHERE lower(full_name)=lower(s.full_name))""",
            tuple(name.lower() for name in missing),
        )
        snapshots = {snapshot["full_name"].lower(): snapshot for snapshot in snapshot_rows}
    for name in missing:
        entries.append(
            {"full_name": name, "reason": "manual_pin", "pinned": 1, **snapshots.get(name.lower(), {})}
        )
    manual = {name.lower() for name in manual_pins()}
    for entry in entries:
        entry["manual"] = entry["full_name"].lower() in manual
    return entries


@app.get("/api/manual-watchlist")
def get_manual_watchlist() -> dict[str, list[str]]:
    return {"repositories": manual_pins()}


@app.post("/api/manual-watchlist", status_code=201)
def add_manual_watchlist(request: PinRequest) -> dict[str, list[str]]:
    full_name = request.full_name.strip().lower()
    if not REPOSITORY_NAME.fullmatch(full_name):
        raise HTTPException(status_code=422, detail="Expected owner/repository")
    with manual_pins_lock():
        values = manual_pins()
        if full_name not in values:
            values.append(full_name)
            save_manual_pins(values)
        return {"repositories": manual_pins()}


@app.delete("/api/manual-watchlist/{full_name:path}")
def remove_manual_watchlist(full_name: str) -> dict[str, list[str]]:
    full_name = full_name.lower()
    if not REPOSITORY_NAME.fullmatch(full_name):
        raise HTTPException(status_code=422, detail="Expected owner/repository")
    with manual_pins_lock():
        save_manual_pins([name for name in manual_pins() if name.lower() != full_name.lower()])
        return {"repositories": manual_pins()}

def refresh_authorised(token: str | None) -> None:
    if not REFRESH_TOKEN or not token or not hmac.compare_digest(token, REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


def runner_request(path: str) -> dict[str, Any]:
    request = Request(
        f"{REFRESH_RUNNER_URL}{path}",
        method="POST" if path == "/run" else "GET",
        headers={"X-Radar-Refresh-Token": REFRESH_TOKEN},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())
    except HTTPError as error:
        try:
            detail = json.loads(error.read())
        except json.JSONDecodeError:
            detail = {"detail": "Refresh runner returned an invalid response"}
        raise HTTPException(status_code=error.code, detail=detail) from error
    except (URLError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="Refresh runner is unavailable") from error


@app.post("/api/internal/refresh", status_code=202)
def refresh(x_radar_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
    refresh_authorised(x_radar_refresh_token)
    return runner_request("/run")


@app.get("/api/internal/refresh")
def refresh_status(x_radar_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
    refresh_authorised(x_radar_refresh_token)
    return runner_request("/status")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
