"""CLI for bounded-scroll-collect. Pure argparse, standard library only."""
from __future__ import annotations

import argparse
import json
import sys

from collector import CollectorConfig, ScrollProvider, collect, resume, save_snapshot

MODES = ("clean", "looping", "ambiguous", "infinite", "crashy")


def cmd_collect(args: argparse.Namespace) -> int:
    provider = ScrollProvider(mode=args.mode, total=args.total, page_size=args.page_size)
    config = CollectorConfig(max_steps=args.max_steps, max_items=args.max_items,
                             max_consecutive_dups=args.max_dups,
                             time_budget_s=args.time_budget,
                             max_requests=args.max_requests,
                             max_tokens=args.max_tokens,
                             default_page_tokens=args.page_tokens)
    report = collect(provider, config)
    out = {k: v for k, v in report.items() if k not in ("items", "state")}
    out["first_items"] = [i.get("id") for i in report["items"][:5]]
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    if args.snapshot:
        with open(args.snapshot, "w", encoding="utf-8") as f:
            json.dump(save_snapshot(report), f, indent=2, sort_keys=True)
        print("snapshot written to %s (resume with: python cli.py resume %s --max-steps N)"
              % (args.snapshot, args.snapshot))
    return 0 if report["complete"] else 1


def cmd_resume(args: argparse.Namespace) -> int:
    with open(args.snapshot, "r", encoding="utf-8") as f:
        snap = json.load(f)
    provider = ScrollProvider(mode=args.mode, total=args.total, page_size=args.page_size)
    config = CollectorConfig(max_steps=args.max_steps, max_items=args.max_items,
                             max_consecutive_dups=args.max_dups,
                             time_budget_s=args.time_budget,
                             max_requests=args.max_requests,
                             max_tokens=args.max_tokens,
                             default_page_tokens=args.page_tokens)
    report = resume(lambda c: provider(c), config, snap)
    out = {k: v for k, v in report.items() if k not in ("items", "state")}
    out["first_items"] = [i.get("id") for i in report["items"][:5]]
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    return 0 if report["complete"] else 1


def cmd_demo(_args: argparse.Namespace) -> int:
    for mode in MODES:
        p = ScrollProvider(mode=mode, total=25, page_size=10)
        r = collect(p, CollectorConfig(max_steps=50, max_items=200, time_budget_s=5.0,
                                       default_page_tokens=10))
        print("%-10s -> %-14s items=%3d pages=%2d errors=%d ledger=req %d/tok %d" %
              (mode, r["stop_reason"], r["item_count"], r["pages_fetched"],
               r["provider_errors"], r["ledger"]["requests"], r["ledger"]["tokens"]))
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
    a.add_argument("--max-requests", type=int, default=None, help="hard cap on requests (request-budget circuit breaker)")
    a.add_argument("--max-tokens", type=int, default=None, help="hard cap on cumulative tokens (token-budget circuit breaker)")
    a.add_argument("--page-tokens", type=int, default=0, help="tokens charged per page when the provider does not report a cost")
    a.add_argument("--report", help="write full JSON report (incl. items) to this path")
    a.add_argument("--snapshot", help="write a resumable checkpoint (items, seen keys, cursor, ledger) to this path")
    a.set_defaults(func=cmd_collect)

    r = sub.add_parser("resume", help="continue a collection from a --snapshot checkpoint with a fresh budget")
    r.add_argument("snapshot", help="path to the snapshot JSON written by collect --snapshot")
    for flag, help_txt in (("--mode", "mock provider behavior"), ("--total", "total items in the mock feed"),
                           ("--page-size", ""), ("--max-steps", "hard cap on fetches"),
                           ("--max-items", "hard cap on collected items"),
                           ("--max-dups", "consecutive no-new-item pages before stopping"),
                           ("--time-budget", "wall-clock seconds"),
                           ("--max-requests", "hard cap on requests"),
                           ("--max-tokens", "hard cap on cumulative tokens"),
                           ("--page-tokens", "tokens charged per silent page"),
                           ("--report", "write full JSON report to this path")):
        kw = {"dest": flag.lstrip("-").replace("-", "_")}
        if flag == "--mode":
            kw["choices"] = MODES
            kw["default"] = "clean"
        elif flag == "--total":
            kw["type"], kw["default"] = int, 25
        elif flag == "--page-size":
            kw["type"], kw["default"] = int, 10
        elif flag == "--max-steps":
            kw["type"], kw["default"] = int, 50
        elif flag == "--max-items":
            kw["type"], kw["default"] = int, 500
        elif flag == "--max-dups":
            kw["type"], kw["default"] = int, 3
        elif flag == "--time-budget":
            kw["type"], kw["default"] = float, 30.0
        elif flag == "--page-tokens":
            kw["type"], kw["default"] = int, 0
        r.add_argument(flag, help=help_txt or None, **kw)
    r.set_defaults(func=cmd_resume)

    d = sub.add_parser("demo", help="run all five mock modes and print stop reasons")
    d.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
