# AI OSS Radar

A daily radar for **viral open-source AI developer tooling**. It ranks unusually fast-growing projects by measured GitHub star velocity, relative growth, acceleration, repository freshness and activity — not raw total stars.

## Architecture

- **GitHub Search API** discovers candidates and hydrates metadata.
- **GitHub Trending** is optional bootstrap data only. Its UI-reported values remain separate from owned history and retain source provenance.
- **SQLite** stores the radar's own periodic snapshots. It is the source of truth after sufficient history exists.
- **Docker Compose** runs collection with a persistent data volume on a VPS.
- **Hermes Cron** is the preferred production delivery interface when Hermes already owns the Telegram gateway.

The precedence rule is strict:

```text
24h delta = measured snapshot ?? GitHub Trending daily ?? N/A
7d delta  = measured snapshot ?? GitHub Trending weekly ?? N/A
```

Missing history is never fabricated as zero.

## Hermes → Telegram delivery

The production installation does **not** need a second Telegram bot token or chat ID. `scripts/hermes_radar_tick.sh` runs the container and prints the finished report to stdout. A Hermes scheduled protocol created with `no_agent=True` delivers that stdout through the existing, already-authorised Hermes Telegram gateway.

This keeps Telegram credentials inside Hermes' active profile and means the radar uses the same communications channel as the operator's current conversation.

For standalone deployments, the direct adapter remains available:

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
uv run ai-oss-radar run --delivery-mode telegram
```

## Configuration

Copy the template outside version control and set the GitHub token:

```bash
cp .env.example .env
# Set GITHUB_TOKEN. Do not commit .env.
```

- `queries.yaml` contains discovery queries, Trending scopes and the snapshot drift tolerance.
- `watchlist.yaml` keeps promising repositories observed even when they no longer match a daily discovery result.
- `TELEGRAM_*` variables are optional and only used for `--delivery-mode telegram`.

## Local development

`uv` is the sole supported Python environment manager.

```bash
uv lock
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ai-oss-radar run --top 10 --delivery-mode stdout
```

The last command requires `GITHUB_TOKEN` and performs live GitHub API requests.

## Container execution

```bash
mkdir -p data
cp .env.example .env
# populate GITHUB_TOKEN in .env
docker compose build
docker compose run --rm radar
```

State and reports persist below `RADAR_DATA_DIR` (default: `./data`):

```text
data/radar.db
data/reports/YYYY-MM-DD.md
data/reports/YYYY-MM-DD.json
```

## Outputs

Each run produces Markdown and JSON. The Markdown Top-10 contains stars, 24h/7d deltas, explicit provenance, relative growth, acceleration, category, age, state and description. The report also adds 2–3 `UNDER_THE_RADAR` candidates chosen for strong relative growth among modest-size projects.

## CI

GitHub Actions is intentionally limited to locked dependency setup, tests and lint. It does not operate the production data store or Telegram delivery. The durable SQLite state remains on the VPS.

## Operational deployment

The production scheduled protocol must be created only after a controlled first collection has succeeded and the Hermes gateway path has been verified. It should execute `scripts/hermes_radar_tick.sh` with `no_agent=True` and deliver to the chosen Hermes Telegram route.
