# Reproduction prompt: AI OSS Viral Radar v0.3.1 (uv-first)

You are implementing and maintaining a production-quality open-source project named `ai-oss-radar`.

Your objective is not to list the largest AI repositories. Build a radar that finds **public AI OSS projects whose attention is increasing unusually fast right now**, especially emerging repositories that total-star sorting misses.

The defining design rule is:

> A 2,000-star repo gaining 600 stars today is normally a stronger viral signal than a 100,000-star repo gaining the same 600, if activity and relevance are comparable.

## Daily product output

Produce a Top-10 of currently viral public AI OSS developer tooling, plus 2-3 `UNDER_THE_RADAR` projects.

Focus on:

- coding agents and agent harnesses
- agent frameworks / multi-agent runtimes
- Agent Skills and reusable agent capabilities
- MCP servers/frameworks/tool routers
- memory, context engineering, RAG and GraphRAG
- local AI / inference infrastructure
- browser agents / computer-use agents
- adjacent AI developer tooling

Do not pad the list with old mega-repos unless they are actively surging again.

## Data architecture: two GitHub sources, never silently mixed

Implement two complementary collection paths.

### Source A — GitHub API + owned snapshots

Use GitHub Search/API for broad discovery and metadata hydration. Persist repository snapshots in SQLite with at least:

- collection timestamp
- full repo name
- direct URL
- description
- current stars
- forks
- created_at
- pushed_at
- language
- topics

Use multiple independent discovery queries covering `ai-agent`, `llm`, `mcp`, `rag`, `local-llm`, `coding agent`, `agent skills`, `context engineering`, `computer use`, `browser agent`, `agent memory`, and recently created repositories with meaningful stars.

Prefer configurable `queries.yaml` and `watchlist.yaml` in a polished implementation.

### Source B — GitHub Trending bootstrap

Collect GitHub Trending as a **separate optional source**:

- `/trending?since=daily`
- `/trending?since=weekly`
- repeat for useful language scopes, at minimum Python, TypeScript and Rust

Parse explicit UI values such as `N stars today` and `N stars this week`.

Store these observations in a separate `trending_signals` table, never in snapshot history. Each row must preserve:

- collection timestamp
- full repo name
- window (`24h` or `7d`)
- star delta
- exact source URL
- scope/language list that produced it

A repo discovered only through Trending must be hydrated through the GitHub API and become a normal candidate.

GitHub Trending is HTML, not a stable API. Treat parser/network failure as non-fatal: API search + owned snapshots must continue working.

## Provenance and precedence rules

For each ranking window choose an effective delta using this precedence:

```text
stars_24h = measured_snapshot_24h ?? github_trending_daily ?? null
stars_7d  = measured_snapshot_7d  ?? github_trending_weekly ?? null
```

This is a hard correctness requirement.

Never overwrite a measured snapshot delta with Trending. Never inject a Trending delta into the historical snapshot series. Never present a UI-derived number as if the radar measured it itself.

Expose provenance for every window:

- `snapshot`
- `github_trending` plus scope/source URL
- `missing`

A report should make provenance human-readable.

## Required metrics

Calculate when effective data exists:

- `stars_24h`
- `stars_7d`
- `growth_ratio_24h = stars_24h / current_total_stars`
- `growth_ratio_7d = stars_7d / current_total_stars`
- `acceleration = stars_24h / avg_daily_stars_of_previous_6_days`
- repo age
- days since last push
- optionally fork velocity

Acceleration can use explicit Trending daily+weekly bootstrap values when owned history is incomplete, but the underlying sources must remain inspectable.

Never substitute zero for a missing historical window.

## Trend states

Use:

- `ACCELERATING`: acceleration >= 1.5x
- `STEADY`: 0.67x < acceleration < 1.5x
- `COOLING`: acceleration <= 0.67x
- `BOOTSTRAP`: at least one explicit growth window comes from Trending, but acceleration is unavailable
- `COLD_START`: no snapshot or Trending growth window exists

Make thresholds configurable later; these defaults are fine.

## Ranking model

Use absolute velocity and relative growth together. Start with:

```text
dynamic_score =
    5.0   * stars_24h
  + 1.2   * stars_7d
  + 250   * min(acceleration, 20)
  + 4500  * growth_ratio_24h
  + 2500  * growth_ratio_7d
```

Then:

```text
viral_score =
    provenance_factor * dynamic_score
  + freshness_bonus
  + recent_activity_bonus
  + small_log_total_stars_prior
  + cold_start_bonus_when_no_growth_signal_exists
```

Suggested provenance confidence:

- both windows measured from snapshots: `1.0`
- mixed snapshot + Trending: about `0.975`
- both windows from Trending: about `0.95`

The exact coefficients are tunable. The behavioral requirements are not:

1. measured history wins over bootstrap data;
2. relative growth can lift a small exploding repo over a giant steady repo;
3. Trending gives useful day-zero velocity rather than waiting seven days;
4. missing data is never fabricated.

## Filtering / relevance

Suppress archived repos, obvious mirrors/forks, spam/keyword farms, unrelated generic matches, and model/dataset dumps with no tooling angle.

A future version may use a lightweight LLM classifier for borderline relevance, but collection/scoring must remain understandable without it.

## Output contract

Generate both Markdown and JSON.

Each Top-10 entry should include:

- repo name + direct URL
- current stars
- 24h delta or `N/A`
- 24h provenance
- 7d delta or `N/A`
- 7d provenance
- growth ratios
- acceleration or `N/A`
- trend state
- category
- repo age
- description
- concise `why_trending`
- one short technical `explain` note describing what is interesting about the project itself

End with 2-3 `UNDER_THE_RADAR` repos: modest total stars, unusually strong relative growth or acceleration.

## Delivery

Telegram is the first delivery adapter. Keep delivery modular for Discord/Slack/email later.

GitHub Actions must:

- support `workflow_dispatch`
- run daily
- restore/persist SQLite history
- collect GitHub API snapshots
- collect Trending bootstrap signals when available
- generate report
- optionally send Telegram
- commit `reports/YYYY-MM-DD.md`

## Python toolchain: mandatory uv/uvx workflow

Use **uv as the canonical and only documented project/environment manager**. This is a hard project requirement, not a preference to ignore when convenient.

Required conventions:

- Python 3.11+; CI should pin/install Python through `uv python install` or the uv setup action
- declare runtime dependencies in `pyproject.toml`
- declare development tools in `[dependency-groups]`, normally `dev`
- generate `uv.lock` with `uv lock` in a normal networked environment and commit it
- bootstrap with `uv sync --group dev`
- run the application with `uv run ai-oss-radar ...`
- run tests with `uv run pytest`
- run lint with `uv run ruff check .`
- use `uvx <tool>` for disposable/one-off Python CLI tools that are intentionally not project dependencies
- GitHub Actions must use `astral-sh/setup-uv` (or an equivalent official/reputable uv setup action), then `uv sync --frozen` and `uv run` once the committed `uv.lock` exists
- do not document or require `python -m venv`, `virtualenv`, `pip install -e`, Poetry, Pipenv, or Conda for normal project use
- do not invoke bare `pip` in CI

The project must be properly packageable so that a clean `uv sync` exposes the `ai-oss-radar` console script. Include an explicit PEP 517 build backend in `pyproject.toml` (for example Hatchling) rather than relying on ambiguous editable-install behavior.

## Engineering requirements

- Python 3.11+
- `httpx`
- a robust HTML parser such as BeautifulSoup for Trending
- SQLite initially
- `pytest` + `ruff`
- typed/simple code; no heavy app framework
- deterministic ranking tie-breaks
- rate-limit aware GitHub client with clear errors
- `.env.example`
- ideally `queries.yaml` and `watchlist.yaml`

## Required tests

At minimum test:

1. growth-ratio calculation;
2. trend-state thresholds;
3. GitHub Trending HTML parser against a local fixture/snippet;
4. Trending daily/weekly values bootstrap missing history and retain provenance;
5. a measured 24h/7d snapshot delta overrides conflicting Trending values;
6. a small repo with the same absolute star gain as a much larger repo can rank higher due to relative growth;
7. total lack of history/signals produces `COLD_START` and `N/A`, not fake zero deltas;
8. deterministic tie ordering.

Do not make tests depend on the live GitHub Trending page.

## Optional later signals

Design future adapters for Hacker News, Reddit and optionally Bluesky. These may add a modest attention bonus but GitHub growth remains the primary signal. Social mentions must not overwhelm measured repository velocity.

## Definition of done

A fresh clone supports this exact uv-first flow:

```bash
uv sync --group dev
export GITHUB_TOKEN=...
uv run ai-oss-radar run --top 12
uv run pytest
uv run ruff check .
```

`uv.lock` must be generated and committed before the repository is considered finished; CI must validate the locked environment with `uv sync --frozen`. If an ad-hoc Python CLI is needed during development and it is not a project dependency, execute it with `uvx`, not a global `pip install`.

Expected behavior by age of installation:

```text
Day 0:
  Trending can bootstrap real source-reported 24h/7d velocity.
  Non-Trending repos remain COLD_START.

Day 1+:
  owned 24h snapshot deltas replace Trending daily values.

Day 7+:
  owned 7d snapshot deltas replace Trending weekly values.
  the radar is fully self-measuring for repeatedly observed repos.
```

Before publishing, run `uv lock`, `uv sync --group dev`, `uv run pytest`, and `uv run ruff check .`; perform a dry collection/report with `uv run ai-oss-radar ...`; create a public GitHub repo, push `main`, enable Actions, document secrets and manually trigger the workflow once.

Reject patches that reintroduce `pip install`, manually managed virtualenv instructions, or a second dependency-management path unless there is an exceptional compatibility reason explicitly documented.
