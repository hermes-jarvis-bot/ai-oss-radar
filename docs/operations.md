# Operations

## Compose protocols

Use `deploy/docker-compose.collector.yml` for one-shot collection and `deploy/docker-compose.dashboard.yml` for the persistent UI. Both require an untracked `deploy/.env` that defines an external `RADAR_DATA_DIR`.

## Verification

```bash
cd collector && uv run ruff check . && uv run pytest
cd ../dashboard && uv run ruff check . && uv run pytest && node --check app/static/app.js
docker compose --env-file deploy/.env -f deploy/docker-compose.collector.yml config
docker compose --env-file deploy/.env -f deploy/docker-compose.dashboard.yml config
```

## Production changes

Before changing a scheduler workdir, data mount, listener address, or report delivery configuration, run the collector against staging data and verify dashboard health separately. Keep the previous deployment checkout available for rollback.
