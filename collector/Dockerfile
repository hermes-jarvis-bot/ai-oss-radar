FROM ghcr.io/astral-sh/uv:0.11.16 AS uv
FROM python:3.12-slim-bookworm

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY README.md queries.yaml watchlist.yaml ./
RUN uv sync --frozen --no-dev
ENTRYPOINT ["/app/.venv/bin/ai-oss-radar"]
