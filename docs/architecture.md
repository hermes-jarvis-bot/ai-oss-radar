# Architecture

AI OSS Radar is one product with two deliberately separated processes.

## Collector

The collector uses GitHub discovery and trending signals, calculates rankings, writes SQLite snapshots, updates dynamic watchlist retention, hydrates manual pins, and produces atomic Markdown/JSON reports. It is intended to run as a bounded one-shot container.

## Dashboard

The dashboard reads the latest SQLite and report state. It is a persistent FastAPI service with mobile-first cards, repository history, manual pins, RU/EN language selection, and dark/light/system themes.

## Least-privilege data flow

```text
collector:  /data             read/write
dashboard:  /data             read-only
            /control/pins.json writable
```

The dashboard must not receive write permission to the SQLite data directory. The isolated control mount exists solely for manual pin state.
