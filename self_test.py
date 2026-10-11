"""Self-test for bounded-scroll-collect: functional / error-path / extreme-edge."""
from __future__ import annotations

import sys

from collector import (CollectorConfig, ScrollProvider, collect, json_key,
                       resume, save_snapshot)

_results = []


def record(family: str, name: str, ok: bool, detail: str = "") -> None:
    _results.append((family, name, "PASS" if ok else "FAIL", detail))


def cfg(**kw):
    base = dict(max_steps=50, max_items=500, max_consecutive_dups=3, time_budget_s=10.0)
    base.update(kw)
    return CollectorConfig(**base)


# ---------------------------------------------------------------- functional


def t_functional():
    r = collect(ScrollProvider("clean", total=25, page_size=10), cfg())
    record("functional", "clean feed drains COMPLETE", r["stop_reason"] == "COMPLETE" and r["item_count"] == 25)

    r = collect(ScrollProvider("clean", total=25), cfg(max_items=12))
    record("functional", "item budget stops at 12", r["stop_reason"] == "BUDGET_ITEMS" and r["item_count"] == 12)

    r = collect(ScrollProvider("infinite", total=25), cfg(max_steps=7))
    record("functional", "step budget stops infinite feed", r["stop_reason"] == "BUDGET_STEPS" and r["pages_fetched"] == 7)

    r = collect(ScrollProvider("looping", total=25), cfg())
    record("functional", "looping feed -> DUP_LIMIT", r["stop_reason"] == "DUP_LIMIT")

    r = collect(ScrollProvider("ambiguous", total=25), cfg())
    record("functional", "ambiguous page -> AMBIGUOUS_PAUSE (no retry)",
           r["stop_reason"] == "AMBIGUOUS_PAUSE")

    r = collect(ScrollProvider("crashy", total=25), cfg())
    record("functional", "provider crash -> PROVIDER_ERROR (no retry)", r["stop_reason"] == "PROVIDER_ERROR")

    # dedup really works: clean feed with dup_ratio re-shows items, none duplicated
    r = collect(ScrollProvider("clean", total=30, page_size=8, dup_ratio=0.4), cfg())
    ids = [i["id"] for i in r["items"]]
    record("functional", "dedup: zero duplicate ids in result", len(ids) == len(set(ids)))

    # ambiguous glitch after collecting some items keeps them
    r = collect(ScrollProvider("ambiguous", total=40, page_size=8, glitch_at=3), cfg())
    record("functional", "items before ambiguity are kept", 0 < r["item_count"] < 40)

    record("functional", "json_key stable for nested dicts",
           json_key({"b": 1, "a": [2, {"z": None}]}) == json_key({"a": [2, {"z": None}], "b": 1}))


# ---------------------------------------------------------------- error paths


def t_error_paths():
    try:
        cfg(max_steps=0)
        record("error", "max_steps=0 rejected", False)
    except ValueError:
        record("error", "max_steps=0 raises ValueError", True)

    try:
        cfg(max_items=-1)
        record("error", "negative max_items rejected", False)
    except ValueError:
        record("error", "negative max_items raises ValueError", True)

    def bad_provider(cursor):
        return {"has_more": True}  # no items key at all

    r = collect(bad_provider, cfg(max_steps=5, max_consecutive_dups=10))
    record("error", "provider returns no items -> drains as empty, stops by budget",
           r["stop_reason"] == "BUDGET_STEPS" and r["item_count"] == 0)

    def error_provider(cursor):
        return {"items": [], "has_more": True, "error": "rate limited"}

    r = collect(error_provider, cfg())
    record("error", "provider error field -> PROVIDER_ERROR", r["stop_reason"] == "PROVIDER_ERROR")

    r = collect(ScrollProvider("clean", total=0), cfg())
    record("error", "empty feed completes with 0 items", r["stop_reason"] == "COMPLETE" and r["item_count"] == 0)


# ---------------------------------------------------------------- extreme edges


def t_extreme_edges():
    r = collect(ScrollProvider("infinite", total=10, page_size=1), cfg(max_steps=1))
    record("edge", "max_steps=1 fetches exactly one page", r["pages_fetched"] == 1 and r["stop_reason"] == "BUDGET_STEPS")

    r = collect(ScrollProvider("clean", total=1000, page_size=100), cfg(max_items=1))
    record("edge", "max_items=1 stops after first item", r["item_count"] == 1 and r["stop_reason"] == "BUDGET_ITEMS")

    r = collect(ScrollProvider("looping", total=20), cfg(max_consecutive_dups=1))
    record("edge", "max_dups=1 stops right after first dup page",
           r["stop_reason"] == "DUP_LIMIT" and r["pages_fetched"] == 2)

    import time
    t0 = time.monotonic()
    r = collect(ScrollProvider("infinite", total=1, page_size=1), cfg(time_budget_s=0.05, max_steps=100000, max_items=10**9))
    dt = time.monotonic() - t0
    record("edge", "tiny time budget honored (<1 s)", r["stop_reason"] == "TIME_BUDGET" and dt < 1.0,
           "%.2fs [measured]" % dt)

    big_item = {"id": "big", "blob": "x" * 100000}
    def big_provider(cursor):
        return {"items": [big_item], "has_more": False}
    r = collect(big_provider, cfg())
    record("edge", "100KB single item collected", r["item_count"] == 1 and r["stop_reason"] == "COMPLETE")

    uni = {"id": "\u4e2d\u6587-\U0001f600", "text": "\u00e9\u00fc"}
    def uni_provider(cursor):
        return {"items": [uni], "has_more": False}
    r = collect(uni_provider, cfg())
    record("edge", "unicode/emoji item keys dedup fine", r["item_count"] == 1)

    r = collect(ScrollProvider("clean", total=25), cfg(max_steps=2))
    record("edge", "feed bigger than step budget -> BUDGET_STEPS with partial items",
           r["stop_reason"] == "BUDGET_STEPS" and 0 < r["item_count"] < 25)


# ------------------------------------------- v0.1.2: cost ledger + snapshot resume


def tok_provider(cursor):
    n = cursor["next"] if cursor else 0
    return {"items": [{"id": "t-%04d" % i} for i in range(n, n + 4)],
            "has_more": n + 4 < 20, "cursor": {"next": n + 4} if n + 4 < 20 else None,
            "tokens": 50}


def t_ledger_and_resume():
    r = collect(ScrollProvider("infinite", total=25), cfg(max_requests=2))
    record("functional", "request budget stops at BUDGET_REQUESTS",
           r["stop_reason"] == "BUDGET_REQUESTS" and r["ledger"]["requests"] == 2,
           str(r["ledger"]))

    r = collect(tok_provider, cfg(max_tokens=120))
    record("functional", "token budget trips BUDGET_TOKENS (cumulative)",
           r["stop_reason"] == "BUDGET_TOKENS" and r["ledger"]["tokens"] == 150,
           str(r["ledger"]))

    r = collect(ScrollProvider("clean", total=25, page_size=10), cfg(default_page_tokens=10))
    record("functional", "default page tokens fill the ledger",
           r["ledger"]["tokens"] == 30 and r["ledger"]["requests"] == 3)

    # snapshot -> resume equals uninterrupted run, zero duplicates across the seam
    full = collect(ScrollProvider("clean", total=30, page_size=8), cfg())
    part = collect(ScrollProvider("clean", total=30, page_size=8), cfg(max_steps=2))
    cont = resume(lambda c: ScrollProvider("clean", total=30, page_size=8)(c), cfg(),
                  save_snapshot(part))
    ids_full = [i["id"] for i in full["items"]]
    ids_cont = [i["id"] for i in cont["items"]]
    record("functional", "resume completes to the same item set",
           full["stop_reason"] == "COMPLETE" and cont["stop_reason"] == "COMPLETE"
           and ids_full == ids_cont)

    try:
        resume(lambda c: {}, cfg(), {"state": {"items": []}})
        record("error", "corrupt snapshot rejected", False)
    except ValueError as e:
        record("error", "corrupt snapshot raises ValueError", "missing" in str(e))

    try:
        cfg(max_requests=0)
        record("error", "max_requests=0 rejected", False)
    except ValueError:
        record("error", "max_requests=0 raises ValueError", True)

    r = collect(tok_provider, cfg(max_tokens=1))
    record("edge", "token breaker fires after page 1 but keeps that page's items",
           r["stop_reason"] == "BUDGET_TOKENS" and r["item_count"] == 4)

    # resume twice (two breaks) still converges with no duplicates
    p1 = collect(ScrollProvider("clean", total=30, page_size=8), cfg(max_steps=1))
    p2 = resume(lambda c: ScrollProvider("clean", total=30, page_size=8)(c),
                cfg(max_steps=1), save_snapshot(p1))
    p3 = resume(lambda c: ScrollProvider("clean", total=30, page_size=8)(c), cfg(),
                save_snapshot(p2))
    ids3 = [i["id"] for i in p3["items"]]
    record("edge", "two-break resume chain completes with unique ids",
           p3["stop_reason"] == "COMPLETE" and len(ids3) == len(set(ids3)))


def main() -> int:
    t_functional()
    t_error_paths()
    t_extreme_edges()
    t_ledger_and_resume()
    fails = [r for r in _results if r[2] == "FAIL"]
    for fam, name, status, detail in _results:
        print("[%s] %-9s %s%s" % (status, fam, name, (" | " + detail) if detail else ""))
    print("\n%d checks, %d failed" % (len(_results), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
