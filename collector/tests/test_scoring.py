import json
from datetime import UTC, datetime, timedelta

from ai_oss_radar import core
from ai_oss_radar.core import (
    Repo,
    TrendingSignal,
    _ratio,
    acceleration_state,
    active_watchlist,
    connect,
    gh_client,
    load_manual_watchlist,
    parse_trending_html,
    ranked,
    store,
    under_the_radar,
    update_dynamic_watchlist,
    write_reports,
)


def repo(name: str, stars: int = 2000) -> Repo:
    now = datetime.now(UTC)
    return Repo(
        name,
        f"https://github.com/{name}",
        "AI coding agent",
        stars,
        10,
        (now - timedelta(days=30)).isoformat(),
        now.isoformat(),
        "Python",
        ["ai-agent"],
    )


def test_growth_ratio_and_states():
    assert _ratio(200, 1000) == 0.2
    assert _ratio(None, 1000) is None
    assert acceleration_state(None) == "COLD_START"
    assert acceleration_state(None, True) == "BOOTSTRAP"
    assert acceleration_state(1.5) == "ACCELERATING"
    assert acceleration_state(0.67) == "COOLING"


def test_parse_github_trending_html():
    signals = parse_trending_html(
        """<article class="Box-row"><h2><a href="/small/viral">small / viral</a></h2><span>1,234 stars today</span></article>""",
        "24h",
        "https://github.com/trending?since=daily",
        "all",
    )
    assert [(signal.full_name, signal.stars_delta) for signal in signals] == [("small/viral", 1234)]


def test_trending_bootstrap_and_snapshot_precedence(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    item = repo("new/agent")
    signals = [
        TrendingSignal("new/agent", "24h", 600, "https://github.com/trending", "all"),
        TrendingSignal("new/agent", "7d", 900, "https://github.com/trending", "all"),
    ]
    store(conn, [item], signals)
    bootstrap = ranked(conn, 1)[0]
    assert bootstrap["stars_24h"] == 600
    assert bootstrap["stars_24h_source"] == "github_trending"

    now = datetime.now(UTC).replace(microsecond=0)
    for stamp, stars in (
        (now - timedelta(hours=24, minutes=20), 1200),
        (now - timedelta(days=7, minutes=10), 1000),
    ):
        conn.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                stamp.isoformat(),
                "new/agent",
                item.html_url,
                item.description,
                stars,
                0,
                item.created_at,
                item.pushed_at,
                "Python",
                "ai-agent",
            ),
        )
    conn.commit()
    measured = ranked(conn, 1)[0]
    assert measured["stars_24h"] == 800
    assert measured["stars_7d"] == 1000
    assert measured["stars_24h_source"] == "snapshot"


def test_small_repo_and_deterministic_tie_order(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    now = datetime.now(UTC).replace(microsecond=0)
    for name, baseline, current in (("small/viral", 1000, 2000), ("big/steady", 100000, 101000)):
        item = repo(name, current)
        conn.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                (now - timedelta(days=1)).isoformat(),
                name,
                item.html_url,
                item.description,
                baseline,
                0,
                item.created_at,
                item.pushed_at,
                "Python",
                "ai-agent",
            ),
        )
        conn.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                now.isoformat(),
                name,
                item.html_url,
                item.description,
                current,
                0,
                item.created_at,
                item.pushed_at,
                "Python",
                "ai-agent",
            ),
        )
    conn.commit()
    items = ranked(conn, 2)
    assert items[0]["repo"] == "small/viral"
    assert [
        item["repo"]
        for item in sorted(items, key=lambda item: (-item["score"], item["repo"].lower()))
    ] == [item["repo"] for item in items]


def test_json_markdown_and_under_the_radar(tmp_path):
    item = {
        "repo": "small/viral",
        "url": "https://github.com/small/viral",
        "description": "agent",
        "stars": 2000,
        "forks": 1,
        "stars_24h": 600,
        "stars_7d": 900,
        "stars_24h_source": "snapshot",
        "stars_7d_source": "snapshot",
        "stars_24h_scope": None,
        "stars_7d_scope": None,
        "growth_ratio_24h": 0.3,
        "growth_ratio_7d": 0.45,
        "acceleration": 2.0,
        "trend_state": "ACCELERATING",
        "age_days": 10,
        "category": "coding-agents",
        "score": 99,
    }
    markdown, report_json, _ = write_reports([item], str(tmp_path))
    assert markdown.exists() and report_json.exists()
    assert under_the_radar([item])[0]["repo"] == "small/viral"



def test_github_client_handles_redirects_explicitly(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    with gh_client() as client:
        assert client.follow_redirects is False

def test_dynamic_watchlist_retains_trending_candidates_for_14_days(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    item = {
        "repo": "small/viral",
        "url": "https://github.com/small/viral",
        "stars": 500,
        "stars_24h": 100,
        "growth_ratio_24h": 0.2,
        "score": 900,
    }
    signal = TrendingSignal("trending/agent", "24h", 100, "https://example.test", "all")
    update_dynamic_watchlist(conn, [item], [signal], ["small/viral"])
    assert set(active_watchlist(conn)) == {"small/viral", "trending/agent"}
    row = conn.execute(
        "SELECT reason, expires_at FROM watchlist_candidates WHERE full_name='small/viral'"
    ).fetchone()
    assert row[0] == "top_ranked"
    assert datetime.fromisoformat(row[1]) > datetime.now(UTC) + timedelta(days=13)


def test_stale_trending_signal_is_not_used_as_current_growth(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    item = repo("old/signal", 1000)
    now = datetime.now(UTC).replace(microsecond=0)
    conn.execute(
        "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            now.isoformat(),
            item.full_name,
            item.html_url,
            item.description,
            item.stars,
            item.forks,
            item.created_at,
            item.pushed_at,
            item.language,
            ",".join(item.topics),
        ),
    )
    conn.execute(
        "INSERT INTO trending_signals VALUES (?,?,?,?,?,?)",
        (
            (now - timedelta(days=30)).isoformat(),
            item.full_name,
            "24h",
            777,
            "https://example.test",
            "all",
        ),
    )
    conn.commit()
    assert ranked(conn, 1)[0]["stars_24h"] is None


def test_dynamic_only_candidate_does_not_refresh_its_own_expiry(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    item = {
        "repo": "old/agent",
        "stars": 100,
        "stars_24h": 1,
        "growth_ratio_24h": 0.01,
        "score": 1,
    }
    update_dynamic_watchlist(conn, [item], [], ["old/agent"], retention_days=1)
    conn.execute(
        "UPDATE watchlist_candidates SET expires_at=? WHERE full_name='old/agent'",
        ((datetime.now(UTC) + timedelta(hours=1)).isoformat(),),
    )
    conn.commit()
    update_dynamic_watchlist(conn, [item], [], [])
    expiry = conn.execute(
        "SELECT expires_at FROM watchlist_candidates WHERE full_name='old/agent'"
    ).fetchone()[0]
    assert datetime.fromisoformat(expiry) < datetime.now(UTC) + timedelta(hours=2)


def test_default_dynamic_watchlist_tracks_top_twelve(tmp_path):
    conn = connect(str(tmp_path / "radar.db"))
    items = [
        {"repo": f"owner/repo-{index}", "stars": 1_000, "stars_24h": None, "growth_ratio_24h": None, "score": 1}
        for index in range(13)
    ]
    update_dynamic_watchlist(conn, items, [], [item["repo"] for item in items])
    assert len(active_watchlist(conn)) == 12


def test_reports_are_published_via_atomic_rename(tmp_path, monkeypatch):
    replacements = []
    original = core.os.replace

    def checked_replace(source, destination):
        assert source.name == f"{destination.name}.tmp"
        replacements.append((source, destination))
        original(source, destination)

    monkeypatch.setattr(core.os, "replace", checked_replace)
    write_reports([], str(tmp_path))
    assert len(replacements) == 2


def test_manual_watchlist_loader_accepts_only_repository_names(tmp_path):
    control = tmp_path / "pins.json"
    control.write_text(
        json.dumps({"repositories": ["owner/project", "invalid name", 42]}), encoding="utf-8"
    )
    assert load_manual_watchlist(str(control)) == ["owner/project"]
