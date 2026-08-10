# AI OSS Radar Dashboard

A mobile-first, local-only dashboard for the **AI OSS Radar** collector. It turns the collector's persistent SQLite history into a practical view of fast-moving AI open-source repositories: ranked candidates, trend signals, a 14-day dynamic watchlist, project history, and persistent manual pins.

![AI OSS Radar Dashboard — dark and light themes](assets/dashboard-en.png)

*One live dashboard view, diagonally split between dark and light modes.*

## Highlights

- **Bilingual UI** — switch between English and Russian; the selection persists in browser storage.
- **Mobile-first cards** — designed for narrow phone screens as well as desktop browsers.
- **Local data refresh** — reloads the accumulated SQLite/JSON data without triggering a GitHub collection run.
- **Candidate history** — inspect star-growth snapshots and project metadata.
- **Two watchlists** — automatic candidates expire after 14 days; manual pins persist until removed.
- **Least-privilege control path** — the dashboard reads `radar.db` read-only and writes only the dedicated manual-pins JSON file.

## Architecture

The dashboard is intentionally separate from the scheduled collector:

```text
Daily collector → SQLite snapshots + reports → read-only dashboard
                                      ↑
                          manual pins control file
```

- The collector runs once daily and writes production data.
- The dashboard runs continuously and never starts collection from its refresh control.
- Production binds to loopback only: `127.0.0.1:8096`.

## Run locally

The dashboard expects a radar SQLite database and a manual-pins control file:

```bash
uv sync --group dev
RADAR_DB=/path/to/radar.db MANUAL_WATCHLIST=/path/to/pins.json \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8096
```

Open [http://127.0.0.1:8096](http://127.0.0.1:8096).

## Production deployment

The production Compose configuration mounts the radar data read-only and exposes the dashboard only on localhost:

```bash
docker compose up -d --build
curl http://127.0.0.1:8096/health
```

For remote access, use an SSH tunnel from a trusted workstation:

```bash
ssh -L 8096:127.0.0.1:8096 root@YOUR_VPS
```

Then browse to `http://127.0.0.1:8096` locally.

## Manual pins

Use the **Watchlist** tab to pin an `owner/repository` pair. Pins are stored in a dedicated JSON control file, have no 14-day expiry, and are hydrated during subsequent daily collection runs. The **Pinned / Мои** tab always renders directly from that authoritative pins list.

## Development checks

```bash
uv run ruff check .
uv run pytest
```

## Security model

- No dashboard write access to the production SQLite database.
- No public listener or reverse-proxy route is configured.
- GitHub credentials and Telegram delivery credentials are not stored in this repository.
