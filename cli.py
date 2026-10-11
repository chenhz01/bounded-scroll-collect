"""CLI for bounded-scroll-collect. Pure argparse, standard library only."""
from __future__ import annotations

import argparse
import json
import sys

from collector import CollectorConfig, ScrollProvider, collect

MODES = ("clean", "looping", "ambiguous", "infinite", "crashy")


def cmd_collect(args: argparse.Namespace) -> int:
    provider = ScrollProvider(mode=args.mode, total=args.total, page_size=args.page_size)
    config = CollectorConfig(max_steps=args.max_steps, max_items=args.max_items,
                             max_consecutive_dups=args.max_dups,
                             time_budget_s=args.time_budget)
    report = collect(provider, config)
    out = {k: v for k, v in report.items() if k != "items"}
    out["first_items"] = [i.get("id") for i in report["items"][:5]]
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    return 0 if report["complete"] else 1


def cmd_demo(_args: argparse.Namespace) -> int:
    for mode in MODES:
        p = ScrollProvider(mode=mode, total=25, page_size=10)
        r = collect(p, CollectorConfig(max_steps=50, max_items=200, time_budget_s=5.0))
        print("%-10s -> %-14s items=%3d pages=%2d errors=%d" %
              (mode, r["stop_reason"], r["item_count"], r["pages_fetched"], r["provider_errors"]))
    print("\nEvery failure mode stops cleanly with a named reason — no blind retries.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bounded-scroll-collect",
                                description="Generic bounded pagination/scroll collector with explicit stop conditions (no platform APIs).")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("collect", help="run the collector against a mock provider")
    a.add_argument("--mode", choices=MODES, default="clean", help="mock provider behavior")
    a.add_argument("--total", type=int, default=25, help="total items in the mock feed")
    a.add_argument("--page-size", type=int, default=10)
    a.add_argument("--max-steps", type=int, default=50, help="hard cap on fetches")
    a.add_argument("--max-items", type=int, default=500, help="hard cap on collected items")
    a.add_argument("--max-dups", type=int, default=3, help="consecutive no-new-item pages before stopping")
    a.add_argument("--time-budget", type=float, default=30.0, help="wall-clock seconds")
    a.add_argument("--report", help="write full JSON report (incl. items) to this path")
    a.set_defaults(func=cmd_collect)

    d = sub.add_parser("demo", help="run all five mock modes and print stop reasons")
    d.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
