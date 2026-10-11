"""bounded-scroll-collect: a generic bounded pagination/scroll collector.

Pure standard library, zero platform APIs (no iOS, no private frameworks).
Abstracts "scroll until done" into explicit stop conditions and budgets:
  - COMPLETE        provider says no more items
  - BUDGET_STEPS    step budget exhausted
  - BUDGET_ITEMS    item budget reached
  - DUP_LIMIT       too many consecutive duplicate pages (provider looping)
  - AMBIGUOUS_PAUSE provider returned an uncertain state -> stop, never
                    blind-retry (the safety core of this design)
  - TIME_BUDGET     wall-clock budget exhausted

Design rule: the collector trusts only the provider's structured return
value, and every failure mode *stops* rather than retries.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

STOP_REASONS = ("COMPLETE", "BUDGET_STEPS", "BUDGET_ITEMS", "BUDGET_REQUESTS",
                "BUDGET_TOKENS", "DUP_LIMIT", "AMBIGUOUS_PAUSE", "TIME_BUDGET",
                "PROVIDER_ERROR")

_SNAPSHOT_KEYS = ("items", "seen", "cursor", "consecutive_dups", "pages",
                  "provider_errors", "requests", "tokens")


class CollectorConfig:
    def __init__(self, max_steps: int = 50, max_items: int = 500,
                 max_consecutive_dups: int = 3, time_budget_s: float = 30.0,
                 dedup_key: Optional[Callable[[dict], Any]] = None,
                 max_requests: Optional[int] = None,
                 max_tokens: Optional[int] = None,
                 default_page_tokens: int = 0):
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        if max_requests is not None and max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self.max_steps = max_steps
        self.max_items = max_items
        self.max_consecutive_dups = max_consecutive_dups
        self.time_budget_s = time_budget_s
        self.dedup_key = dedup_key or default_key
        self.max_requests = max_requests
        self.max_tokens = max_tokens
        self.default_page_tokens = default_page_tokens


def json_key(item: Any) -> Any:
    """Fallback dedup key: canonical repr of the item itself."""
    if isinstance(item, dict):
        return tuple(sorted((k, json_key(v)) for k, v in item.items()))
    if isinstance(item, (list, tuple)):
        return tuple(json_key(v) for v in item)
    return item


def default_key(item: Any) -> Any:
    """Default dedup key: the item's 'id' field when present (feeds re-show
    the same entity with mutated metadata); else a canonical repr of the item."""
    if isinstance(item, dict) and "id" in item:
        return ("id", json_key(item["id"]))
    return json_key(item)


def _canon(key: Any) -> str:
    """Canonical string form of a dedup key (JSON, sorted keys, repr fallback)."""
    return json.dumps(key, sort_keys=True, default=repr)


def collect(fetch: Callable[[Optional[dict]], dict], config: CollectorConfig,
            state: Optional[dict] = None) -> dict:
    """Run a bounded collection loop.

    fetch(cursor) -> {"items": [...], "has_more": bool, "cursor": next|None,
                      "ambiguous": bool (optional), "error": str (optional),
                      "tokens": int (optional, page cost for the ledger)}
    The provider contract: on any page where state can't be trusted, return
    ambiguous=True. The collector then PAUSES. It never re-fetches on its own.

    state: optional dict from save_snapshot() to resume a prior session with
    items, seen-keys, cursor, and ledger counters restored.
    """
    if state is not None:
        missing = [k for k in _SNAPSHOT_KEYS if k not in state]
        if missing:
            raise ValueError("bad snapshot: missing %s" % ", ".join(missing))
        items = list(state["items"])
        seen = set(state["seen"])
        cursor = state["cursor"]
        consecutive_dups = state["consecutive_dups"]
        pages = state["pages"]
        provider_errors = state["provider_errors"]
        requests = state["requests"]
        tokens = state["tokens"]
    else:
        items: List[Any] = []
        seen = set()
        cursor = None
        consecutive_dups = 0
        pages = 0
        provider_errors = 0
        requests = 0
        tokens = 0

    start = time.monotonic()
    stop_reason = None

    while True:
        if pages >= config.max_steps:
            stop_reason = "BUDGET_STEPS"
            break
        if config.max_requests is not None and requests >= config.max_requests:
            stop_reason = "BUDGET_REQUESTS"
            break
        if time.monotonic() - start >= config.time_budget_s:
            stop_reason = "TIME_BUDGET"
            break

        requests += 1
        try:
            page = fetch(cursor)
        except Exception:  # provider blew up: stop, don't retry
            provider_errors += 1
            stop_reason = "PROVIDER_ERROR"
            break

        if page.get("error"):
            provider_errors += 1
            stop_reason = "PROVIDER_ERROR"
            break

        if page.get("ambiguous"):
            stop_reason = "AMBIGUOUS_PAUSE"
            break

        tokens += int(page.get("tokens", config.default_page_tokens) or 0)

        new_count = 0
        dup_count = 0
        for item in page.get("items", []):
            key = _canon(config.dedup_key(item))
            if key in seen:
                dup_count += 1
                continue
            if len(items) >= config.max_items:
                stop_reason = "BUDGET_ITEMS"
                break
            seen.add(key)
            items.append(item)
            new_count += 1
        if stop_reason == "BUDGET_ITEMS":
            break

        pages += 1
        consecutive_dups = consecutive_dups + 1 if new_count == 0 else 0
        if consecutive_dups >= config.max_consecutive_dups:
            stop_reason = "DUP_LIMIT"
            break

        if config.max_tokens is not None and tokens >= config.max_tokens:
            stop_reason = "BUDGET_TOKENS"
            break

        if not page.get("has_more"):
            stop_reason = "COMPLETE"
            break
        cursor = page.get("cursor")

    elapsed = time.monotonic() - start
    return {"stop_reason": stop_reason, "items": items, "item_count": len(items),
            "pages_fetched": pages, "elapsed_s": round(elapsed, 3),
            "provider_errors": provider_errors,
            "complete": stop_reason == "COMPLETE",
            "ledger": {"requests": requests, "tokens": tokens,
                       "limit_requests": config.max_requests,
                       "limit_tokens": config.max_tokens},
            "state": {"items": items, "seen": sorted(seen), "cursor": cursor,
                      "consecutive_dups": consecutive_dups, "pages": pages,
                      "provider_errors": provider_errors,
                      "requests": requests, "tokens": tokens}}


def save_snapshot(report: dict) -> dict:
    """Extract the resumable state from a collect() report (JSON-serializable)."""
    return {"version": 1, "state": dict(report["state"])}


def resume(fetch: Callable[[Optional[dict]], dict], config: CollectorConfig,
           snapshot: dict) -> dict:
    """Continue a collection from save_snapshot() output with a fresh budget.

    Duplicate-free guarantee across the seam: seen-keys and cursor are restored
    verbatim. Note: call-count-dependent provider behavior (e.g. the mock's
    ambiguous glitch position) restarts with the new fetch closure — pass a
    provider whose position depends on cursor, not call count, for exact parity.
    """
    return collect(fetch, config, state=snapshot.get("state", snapshot))


# ---------------------------------------------------------------- mock provider

class ScrollProvider:
    """Deterministic mock feed for tests/demos.

    modes: "clean" (finite, dedup-safe), "looping" (repeats same items),
           "ambiguous" (glitches mid-stream), "infinite" (never ends),
           "crashy" (raises after N pages).
    """

    def __init__(self, mode: str = "clean", total: int = 25, page_size: int = 10,
                 glitch_at: int = 3, crash_after: int = 2, dup_ratio: float = 0.3):
        self.mode = mode
        self.total = total
        self.page_size = page_size
        self.glitch_at = glitch_at
        self.crash_after = crash_after
        self.dup_ratio = dup_ratio
        self.calls = 0

    def __call__(self, cursor: Optional[dict]) -> dict:
        self.calls += 1
        start = cursor["next"] if cursor else 0
        if self.mode == "crashy" and self.calls > self.crash_after:
            raise RuntimeError("simulated provider crash")
        if self.mode == "ambiguous" and self.calls == self.glitch_at:
            return {"items": [], "has_more": True, "cursor": {"next": start},
                    "ambiguous": True, "reason": "widget tree not settled"}
        end = min(start + self.page_size, self.total)
        items = [{"id": "item-%05d" % i, "text": "content %d" % i} for i in range(start, end)]
        if self.mode == "looping" and start > 0:
            # the endless-scroll trap: feed claims has_more forever but every
            # subsequent page re-emits the first page's items
            stale = [{"id": "item-%05d" % i, "text": "stale"} for i in range(self.page_size)]
            return {"items": stale, "has_more": True,
                    "cursor": {"next": start + self.page_size}}
        if self.mode == "clean" and 0 < start and self.dup_ratio > 0:
            # realistic feeds re-show a couple of already-seen items per page
            # (prepended; new items are never dropped)
            k = max(1, int(len(items) * self.dup_ratio))
            items = [{"id": "item-%05d" % max(0, start - j), "text": "seen again"} for j in range(k)] + items
        if self.mode == "infinite":
            # truly endless: always brand-new ids, has_more never false
            items = [{"id": "inf-%06d" % (start + i), "text": "content %d" % (start + i)}
                     for i in range(self.page_size)]
            return {"items": items, "has_more": True, "cursor": {"next": start + self.page_size}}
        has_more = end < self.total
        nxt = end if has_more else None
        return {"items": items, "has_more": has_more, "cursor": {"next": nxt} if has_more else None}
