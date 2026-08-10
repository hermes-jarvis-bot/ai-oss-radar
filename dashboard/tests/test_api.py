import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def seed(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """CREATE TABLE snapshots (ts TEXT, full_name TEXT, html_url TEXT, description TEXT,
        stars INTEGER, forks INTEGER, created_at TEXT, pushed_at TEXT, language TEXT, topics TEXT);
        CREATE TABLE watchlist_candidates (full_name TEXT, added_at TEXT, expires_at TEXT,
        reason TEXT, pinned INTEGER, last_seen_at TEXT);"""
    )
    conn.execute(
        "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "2026-08-09T06:00:00+00:00",
            "demo/agent",
            "https://github.com/demo/agent",
            "demo",
            100,
            1,
            "2026-01-01T00:00:00+00:00",
            "2026-08-09T00:00:00+00:00",
            "Python",
            "ai",
        ),
    )
    conn.execute(
        "INSERT INTO watchlist_candidates VALUES (?,?,?,?,?,?)",
        (
            "demo/agent",
            "2026-08-09T06:00:00+00:00",
            "2026-08-23T06:00:00+00:00",
            "top_ranked",
            0,
            "2026-08-09T06:00:00+00:00",
        ),
    )
    conn.commit()


def test_summary_and_history(tmp_path, monkeypatch):
    path = tmp_path / "radar.db"
    seed(path)
    monkeypatch.setattr(main, "DB_PATH", str(path))
    client = TestClient(main.app)
    assert client.get("/health").json()["snapshots"] == 1
    assert client.get("/api/summary").json()["repositories"][0]["full_name"] == "demo/agent"
    history = client.get("/api/repositories/demo/agent/history").json()
    assert history["history"][0]["stars"] == 100
    assert history["summary"]["description"] == "demo"
    assert client.get("/api/watchlist").json()[0]["reason"] == "top_ranked"


def test_repository_current_stars_comes_from_latest_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "radar.db"
    seed(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "2026-08-10T06:00:00+00:00",
            "demo/agent",
            "https://github.com/demo/agent",
            "demo",
            90,
            1,
            "2026-01-01T00:00:00+00:00",
            "2026-08-10T00:00:00+00:00",
            "Python",
            "ai",
        ),
    )
    conn.commit()
    monkeypatch.setattr(main, "DB_PATH", str(path))
    response = TestClient(main.app).get("/api/repositories").json()[0]
    assert response["current_stars"] == 90
    assert response["last_seen"] == "2026-08-10T06:00:00+00:00"


def test_empty_database_returns_explicit_empty_summary(tmp_path, monkeypatch):
    path = tmp_path / "radar.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE snapshots (ts TEXT, full_name TEXT)")
    conn.commit()
    monkeypatch.setattr(main, "DB_PATH", str(path))
    client = TestClient(main.app)
    assert client.get("/health").json()["latest_snapshot"] is None
    assert client.get("/api/summary").json() == {"latest_snapshot": None, "repositories": []}


def test_mobile_empty_and_expiry_guards_are_present():
    source = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    assert "!health.latest_snapshot" in source
    assert "remaining >= 0 && remaining < 3 * 864e5" in source
    assert "item.html_url || item.url" in source
    assert "Потяните страницу вниз" in (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()


def test_manual_watchlist_can_pin_and_unpin_without_writing_radar_db(tmp_path, monkeypatch):
    path = tmp_path / "radar.db"
    control = tmp_path / "control" / "pins.json"
    seed(path)
    monkeypatch.setattr(main, "DB_PATH", str(path))
    monkeypatch.setattr(main, "CONTROL_PATH", control)
    client = TestClient(main.app)
    assert (
        client.post("/api/manual-watchlist", json={"full_name": "owner/project"}).status_code == 201
    )
    assert client.get("/api/manual-watchlist").json() == {"repositories": ["owner/project"]}
    assert client.get("/api/watchlist").json()[-1]["reason"] == "manual_pin"
    assert (
        client.post("/api/manual-watchlist", json={"full_name": "invalid name"}).status_code == 422
    )
    assert client.delete("/api/manual-watchlist/owner/project").json() == {"repositories": []}
    assert control.exists()
