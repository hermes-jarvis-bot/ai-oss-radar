from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

API = "https://api.github.com"
GITHUB = "https://github.com"
DEFAULT_QUERIES = ["topic:ai-agent stars:>100", "topic:mcp stars:>50"]
DEFAULT_SCOPES = ["all", "python", "typescript", "rust"]
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
KEYWORDS = {
    "coding-agents": ["coding agent", "code agent", "claude code", "codex", "cursor"],
    "skills": ["agent skill", "skills", "skill.md"],
    "mcp-tools": ["mcp", "model context protocol"],
    "memory-context-rag": ["memory", "context engineering", "rag", "retrieval", "graph rag"],
    "local-ai-inference": ["local llm", "inference", "ollama", "vllm", "mlx"],
    "browser-computer-use": ["browser agent", "computer use", "browser automation"],
    "agent-frameworks": ["agent framework", "multi-agent", "agentic"],
}


@dataclass
class Repo:
    full_name: str
    html_url: str
    description: str
    stars: int
    forks: int
    created_at: str
    pushed_at: str
    language: str
    topics: list[str]


@dataclass
class TrendingSignal:
    full_name: str
    window: str
    stars_delta: int
    source_url: str
    scope: str


def load_config(path: str = "queries.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {
            "search_queries": DEFAULT_QUERIES,
            "trending_scopes": DEFAULT_SCOPES,
            "snapshot_tolerance_hours": 3,
        }
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return {
        "search_queries": data.get("search_queries", DEFAULT_QUERIES),
        "trending_scopes": data.get("trending_scopes", DEFAULT_SCOPES),
        "snapshot_tolerance_hours": data.get("snapshot_tolerance_hours", 3),
    }


def load_watchlist(path: str = "watchlist.yaml") -> list[str]:
    watchlist_path = Path(path)
    if not watchlist_path.exists():
        return []
    data = yaml.safe_load(watchlist_path.read_text(encoding="utf-8")) or {}
    return [str(name).lower() for name in data.get("repositories", [])]


def load_manual_watchlist(path: str) -> list[str]:
    """Load operator-pinned repositories from the dashboard control file."""
    control_path = Path(path)
    if not control_path.exists():
        return []
    try:
        data = json.loads(control_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    names = data.get("repositories", []) if isinstance(data, dict) else []
    return [name for name in names if isinstance(name, str) and REPOSITORY_NAME.fullmatch(name)]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
            ts TEXT NOT NULL, full_name TEXT NOT NULL, html_url TEXT NOT NULL,
            description TEXT, stars INTEGER NOT NULL, forks INTEGER NOT NULL,
            created_at TEXT NOT NULL, pushed_at TEXT NOT NULL, language TEXT, topics TEXT,
            PRIMARY KEY (ts, full_name))"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_repo_ts ON snapshots(full_name, ts)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trending_signals (
            ts TEXT NOT NULL, full_name TEXT NOT NULL, window TEXT NOT NULL,
            stars_delta INTEGER NOT NULL, source_url TEXT NOT NULL, scope TEXT NOT NULL,
            PRIMARY KEY (ts, full_name, window, scope))"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trending_repo_ts ON trending_signals(full_name, ts)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS watchlist_candidates (
            full_name TEXT PRIMARY KEY,
            added_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT NOT NULL)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchlist_expiry ON watchlist_candidates(expires_at)"
    )
    conn.commit()
    return conn


def active_watchlist(conn: sqlite3.Connection) -> list[str]:
    """Return automatic candidates still inside retention plus manually pinned repos."""
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    conn.execute("DELETE FROM watchlist_candidates WHERE pinned=0 AND expires_at<?", (now,))
    conn.commit()
    return [
        row[0]
        for row in conn.execute(
            "SELECT full_name FROM watchlist_candidates WHERE pinned=1 OR expires_at>=?",
            (now,),
        )
    ]


def update_dynamic_watchlist(
    conn: sqlite3.Connection,
    items: list[dict],
    trending_signals: Iterable[TrendingSignal],
    independently_discovered: Iterable[str] = (),
    retention_days: int = 14,
) -> None:
    """Retain candidates after a fresh, independent signal for bounded follow-up."""
    now = datetime.now(UTC).replace(microsecond=0)
    expires = (now + timedelta(days=retention_days)).isoformat()
    independent = {name.lower() for name in independently_discovered}
    candidates: dict[str, str] = {}
    for item in items[:10]:
        if item["repo"].lower() in independent:
            candidates[item["repo"]] = "top_ranked"
    for item in under_the_radar(items):
        if item["repo"].lower() in independent:
            candidates.setdefault(item["repo"], "under_the_radar")
    for signal in trending_signals:
        candidates.setdefault(signal.full_name, f"github_trending_{signal.window}")
    conn.executemany(
        """INSERT INTO watchlist_candidates(full_name, added_at, expires_at, reason, pinned, last_seen_at)
           VALUES (?,?,?,?,0,?)
           ON CONFLICT(full_name) DO UPDATE SET
             expires_at=excluded.expires_at,
             reason=excluded.reason,
             last_seen_at=excluded.last_seen_at""",
        [
            (name, now.isoformat(), expires, reason, now.isoformat())
            for name, reason in candidates.items()
        ],
    )
    conn.commit()


def gh_client() -> httpx.Client:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("RADAR_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN or RADAR_GITHUB_TOKEN is required for collection")
    return httpx.Client(
        base_url=API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-oss-radar",
            "Authorization": f"Bearer {token}",
        },
        timeout=30,
    )


def _is_relevant(item: dict) -> bool:
    if item.get("archived") or item.get("fork") or item.get("disabled"):
        return False
    text = " ".join(
        [
            item.get("full_name", ""),
            item.get("description") or "",
            " ".join(item.get("topics") or []),
            item.get("language") or "",
        ]
    ).lower()
    if any(term in text for term in ("dataset", "model weights", "model zoo", "awesome-")):
        return False
    return (
        any(keyword in text for words in KEYWORDS.values() for keyword in words)
        or "ai" in text
        or "llm" in text
    )


def _repo_from_api(item: dict) -> Repo:
    return Repo(
        full_name=item["full_name"],
        html_url=item["html_url"],
        description=item.get("description") or "",
        stars=item["stargazers_count"],
        forks=item["forks_count"],
        created_at=item["created_at"],
        pushed_at=item["pushed_at"],
        language=item.get("language") or "",
        topics=item.get("topics") or [],
    )


def discover_search(queries: list[str], limit_per_query: int = 50) -> dict[str, Repo]:
    found: dict[str, Repo] = {}
    with gh_client() as client:
        for query in queries:
            response = client.get(
                "/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": limit_per_query,
                },
            )
            response.raise_for_status()
            for item in response.json().get("items", []):
                if _is_relevant(item):
                    repo = _repo_from_api(item)
                    found[repo.full_name.lower()] = repo
    return found


def discover_watchlist(names: list[str]) -> dict[str, Repo]:
    found: dict[str, Repo] = {}
    if not names:
        return found
    with gh_client() as client:
        for name in sorted(set(names)):
            response = client.get(f"/repos/{name}")
            if response.status_code == 404:
                continue
            response.raise_for_status()
            item = response.json()
            if not item.get("archived") and not item.get("fork"):
                repo = _repo_from_api(item)
                found[repo.full_name.lower()] = repo
    return found


def _parse_int(text: str) -> int | None:
    match = re.search(r"([\d,]+)", text)
    return int(match.group(1).replace(",", "")) if match else None


def parse_trending_html(
    html: str, window: str, source_url: str, scope: str
) -> list[TrendingSignal]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[TrendingSignal] = []
    needle = "stars today" if window == "24h" else "stars this week"
    for article in soup.select("article.Box-row"):
        link = article.select_one("h2 a[href]")
        if not link:
            continue
        name = link.get("href", "").strip("/")
        if name.count("/") != 1:
            continue
        delta = next(
            (
                _parse_int(" ".join(span.stripped_strings))
                for span in article.select("span")
                if needle in " ".join(span.stripped_strings).lower()
            ),
            None,
        )
        if delta is not None:
            out.append(TrendingSignal(name, window, delta, source_url, scope))
    return out


def discover_trending(scopes: list[str]) -> tuple[dict[str, Repo], list[TrendingSignal]]:
    signals: dict[tuple[str, str], TrendingSignal] = {}
    names: set[str] = set()
    with httpx.Client(
        base_url=GITHUB, headers={"User-Agent": "ai-oss-radar"}, timeout=30, follow_redirects=True
    ) as web:
        for scope in scopes:
            path = "/trending" + ("" if scope == "all" else f"/{scope}")
            for since, window in (("daily", "24h"), ("weekly", "7d")):
                response = web.get(path, params={"since": since})
                response.raise_for_status()
                for signal in parse_trending_html(response.text, window, str(response.url), scope):
                    names.add(signal.full_name)
                    key = (signal.full_name.lower(), signal.window)
                    if key not in signals or signal.stars_delta > signals[key].stars_delta:
                        signals[key] = signal
    repos = discover_watchlist(sorted(names))
    return repos, list(signals.values())


def discover(
    config_path: str = "queries.yaml",
    watchlist_path: str = "watchlist.yaml",
    dynamic_watchlist: Iterable[str] = (),
    manual_watchlist: Iterable[str] = (),
) -> tuple[dict[str, Repo], list[TrendingSignal], set[str]]:
    config = load_config(config_path)
    search_repos = discover_search(config["search_queries"])
    static_repos = discover_watchlist(load_watchlist(watchlist_path))
    dynamic_repos = discover_watchlist(list(dynamic_watchlist))
    manual_repos = discover_watchlist(list(manual_watchlist))
    repos = {**search_repos, **static_repos, **dynamic_repos, **manual_repos}
    try:
        trending_repos, signals = discover_trending(config["trending_scopes"])
    except (httpx.HTTPError, ValueError):
        trending_repos, signals = {}, []
    repos.update(trending_repos)
    independently_discovered = set(search_repos) | set(static_repos) | set(trending_repos)
    return repos, signals, independently_discovered


def store(
    conn: sqlite3.Connection, repos: Iterable[Repo], trending_signals: Iterable[TrendingSignal] = ()
) -> str:
    ts = datetime.now(UTC).replace(microsecond=0).isoformat()
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                ts,
                repo.full_name,
                repo.html_url,
                repo.description,
                repo.stars,
                repo.forks,
                repo.created_at,
                repo.pushed_at,
                repo.language,
                ",".join(repo.topics),
            )
            for repo in repos
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO trending_signals VALUES (?,?,?,?,?,?)",
        [
            (
                ts,
                signal.full_name,
                signal.window,
                signal.stars_delta,
                signal.source_url,
                signal.scope,
            )
            for signal in trending_signals
        ],
    )
    conn.commit()
    return ts


def category(text: str) -> str:
    lowered = text.lower()
    scored = [(sum(word in lowered for word in words), label) for label, words in KEYWORDS.items()]
    return (
        max(scored, default=(0, "ai-tooling"))[1]
        if max(scored, default=(0, "ai-tooling"))[0]
        else "ai-tooling"
    )


def nearest_snapshot(
    conn: sqlite3.Connection, repo: str, target: datetime, tolerance_hours: int = 3
):
    start = (target - timedelta(hours=tolerance_hours)).isoformat()
    end = (target + timedelta(hours=tolerance_hours)).isoformat()
    return conn.execute(
        """SELECT ts, stars FROM snapshots WHERE full_name=? AND ts BETWEEN ? AND ?
           ORDER BY ABS(julianday(ts) - julianday(?)) LIMIT 1""",
        (repo, start, end, target.isoformat()),
    ).fetchone()


def latest_trending_signal(
    conn: sqlite3.Connection,
    repo: str,
    window: str,
    at: datetime,
    freshness_hours: int,
):
    earliest = (at - timedelta(hours=freshness_hours)).isoformat()
    return conn.execute(
        """SELECT stars_delta, source_url, scope, ts FROM trending_signals
           WHERE lower(full_name)=lower(?) AND window=? AND ts BETWEEN ? AND ?
           ORDER BY ts DESC LIMIT 1""",
        (repo, window, earliest, at.isoformat()),
    ).fetchone()


def acceleration_state(acceleration: float | None, has_any_growth_signal: bool = False) -> str:
    if acceleration is None:
        return "BOOTSTRAP" if has_any_growth_signal else "COLD_START"
    if acceleration >= 1.5:
        return "ACCELERATING"
    if acceleration <= 0.67:
        return "COOLING"
    return "STEADY"


def _ratio(delta: int | None, stars: int) -> float | None:
    return min(max(delta / stars, 0.0), 1.0) if delta is not None and stars > 0 else None


def _effective_delta(measured: int | None, trending_row):
    if measured is not None:
        return measured, "snapshot", None, None
    if trending_row:
        delta, source_url, scope, _ = trending_row
        return int(delta), "github_trending", source_url, scope
    return None, "missing", None, None


def ranked(conn: sqlite3.Connection, top: int = 10, tolerance_hours: int = 3) -> list[dict]:
    latest_ts = conn.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
    if not latest_ts:
        return []
    now = datetime.fromisoformat(latest_ts)
    rows = conn.execute(
        """SELECT full_name, html_url, description, stars, forks, created_at, pushed_at, language, topics
                           FROM snapshots WHERE ts=?""",
        (latest_ts,),
    ).fetchall()
    out = []
    for full_name, url, desc, stars, forks, created, pushed, language, topics in rows:
        s24 = nearest_snapshot(conn, full_name, now - timedelta(hours=24), tolerance_hours)
        s7 = nearest_snapshot(conn, full_name, now - timedelta(days=7), tolerance_hours)
        measured24 = max(stars - s24[1], 0) if s24 else None
        measured7 = max(stars - s7[1], 0) if s7 else None
        d24, source24, url24, scope24 = _effective_delta(
            measured24, latest_trending_signal(conn, full_name, "24h", now, tolerance_hours)
        )
        d7, source7, url7, scope7 = _effective_delta(
            measured7, latest_trending_signal(conn, full_name, "7d", now, tolerance_hours)
        )
        accel = None
        if d24 is not None and d7 is not None:
            accel = d24 / max((max(d7 - d24, 0) / 6), 1)
        ratio24, ratio7 = _ratio(d24, stars), _ratio(d7, stars)
        age_days = max((now - datetime.fromisoformat(created)).days, 1)
        pushed_days = max((now - datetime.fromisoformat(pushed)).days, 0)
        dynamic = 5 * (d24 or 0) + 1.2 * (d7 or 0) + 250 * min(accel or 0, 20)
        dynamic += 4500 * (ratio24 or 0) + 2500 * (ratio7 or 0)
        factor = (
            0.95
            if source24 == source7 == "github_trending"
            else 0.975
            if "github_trending" in {source24, source7}
            else 1.0
        )
        cold_start = min(stars / age_days, 1000) * 1.5 if d24 is None and d7 is None else 0
        score = (
            factor * dynamic
            + max(0, 600 - min(age_days, 365) * 1.2)
            + max(0, 250 - pushed_days * 20)
            + 40 * math.log10(stars + 10)
            + cold_start
        )
        out.append(
            {
                "repo": full_name,
                "url": url,
                "description": desc,
                "stars": stars,
                "forks": forks,
                "stars_24h": d24,
                "stars_7d": d7,
                "stars_24h_source": source24,
                "stars_7d_source": source7,
                "stars_24h_source_url": url24,
                "stars_7d_source_url": url7,
                "stars_24h_scope": scope24,
                "stars_7d_scope": scope7,
                "growth_ratio_24h": ratio24,
                "growth_ratio_7d": ratio7,
                "acceleration": accel,
                "trend_state": acceleration_state(accel, d24 is not None or d7 is not None),
                "age_days": age_days,
                "category": category(" ".join([full_name, desc, topics or "", language or ""])),
                "score": score,
            }
        )
    return sorted(out, key=lambda item: (-item["score"], item["repo"].lower()))[:top]


def under_the_radar(items: list[dict], count: int = 3) -> list[dict]:
    modest = [item for item in items if item["stars"] <= 10_000 and item["stars_24h"] is not None]
    return sorted(
        modest,
        key=lambda item: (-(item["growth_ratio_24h"] or 0), -item["score"], item["repo"].lower()),
    )[:count]


def _delta(value: int | None, window: str) -> str:
    return f"+{value:,}/{window}" if value is not None else f"N/A/{window}"


def _source(source: str, scope: str | None) -> str:
    return (
        "snapshot"
        if source == "snapshot"
        else f"GitHub Trending/{scope or 'all'}"
        if source == "github_trending"
        else "N/A"
    )


def render_markdown(items: list[dict], underground: list[dict] | None = None) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# AI OSS Radar — {stamp}",
        "",
        "Snapshot history takes precedence; Trending signals are explicit bootstrap data.",
        "",
    ]
    for index, item in enumerate(items, 1):
        acceleration = f"{item['acceleration']:.2f}x" if item["acceleration"] is not None else "N/A"
        lines.extend(
            [
                f"## {index}. [{item['repo']}]({item['url']})",
                f"- Stars: **{item['stars']:,}** · {_delta(item['stars_24h'], '24h')} · {_delta(item['stars_7d'], '7d')}",
                f"- Provenance: 24h **{_source(item['stars_24h_source'], item['stars_24h_scope'])}** · 7d **{_source(item['stars_7d_source'], item['stars_7d_scope'])}**",
                f"- Growth: 24h **{(item['growth_ratio_24h'] or 0):.1%}** · 7d **{(item['growth_ratio_7d'] or 0):.1%}** · acceleration **{acceleration}**",
                f"- `{item['category']}` · age {item['age_days']}d · **{item['trend_state']}**",
                f"- {item['description'] or 'No description'}",
                "",
            ]
        )
    if underground:
        lines.extend(["## UNDER_THE_RADAR", ""])
        for item in underground:
            lines.append(
                f"- [{item['repo']}]({item['url']}) — {_delta(item['stars_24h'], '24h')}; relative growth {(item['growth_ratio_24h'] or 0):.1%}."
            )
    return "\n".join(lines)


def write_reports(items: list[dict], reports_dir: str) -> tuple[Path, Path, str]:
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    underground = under_the_radar(items)
    text = render_markdown(items, underground)
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    markdown_path, json_path = directory / f"{date}.md", directory / f"{date}.json"
    _atomic_write_text(markdown_path, text)
    _atomic_write_text(
        json_path,
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "top": items,
                "under_the_radar": underground,
            },
            indent=2,
        ),
    )
    return markdown_path, json_path, text


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def send_telegram(text: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    with httpx.Client(timeout=20) as client:
        for chunk in (text[i : i + 3900] for i in range(0, len(text), 3900)):
            response = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            )
            response.raise_for_status()
    return True
