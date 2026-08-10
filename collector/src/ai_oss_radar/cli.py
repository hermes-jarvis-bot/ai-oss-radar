from __future__ import annotations

import argparse
import sys

from .core import (
    active_watchlist,
    connect,
    discover,
    load_config,
    load_manual_watchlist,
    ranked,
    send_telegram,
    store,
    update_dynamic_watchlist,
    write_reports,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-oss-radar")
    parser.add_argument("command", choices=["collect", "report", "run"])
    parser.add_argument("--db", default="radar.db")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--config", default="queries.yaml")
    parser.add_argument("--watchlist", default="watchlist.yaml")
    parser.add_argument("--manual-watchlist", default="/data/manual-watchlist/pins.json")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--delivery-mode", choices=["stdout", "telegram", "none"], default="none")
    args = parser.parse_args()

    conn = connect(args.db)
    if args.command in {"collect", "run"}:
        repos, trending_signals, independently_discovered = discover(
            args.config,
            args.watchlist,
            active_watchlist(conn),
            load_manual_watchlist(args.manual_watchlist),
        )
        stamp = store(conn, repos.values(), trending_signals)
        tolerance = int(load_config(args.config)["snapshot_tolerance_hours"])
        update_dynamic_watchlist(
            conn, ranked(conn, 50, tolerance), trending_signals, independently_discovered
        )
        print(
            f"stored {len(repos)} repositories and {len(trending_signals)} Trending signals at {stamp}",
            file=sys.stderr,
        )

    if args.command in {"report", "run"}:
        tolerance = int(load_config(args.config)["snapshot_tolerance_hours"])
        items = ranked(conn, args.top, tolerance)
        markdown_path, json_path, text = write_reports(items, args.reports_dir)
        print(f"reports: {markdown_path} {json_path}", file=sys.stderr)
        if args.delivery_mode == "stdout":
            print(text)
        elif args.delivery_mode == "telegram":
            print("telegram:", "sent" if send_telegram(text) else "not configured")


if __name__ == "__main__":
    main()
