# bounded-scroll-collect

A generic bounded collection loop for paginated and scroll-based feeds: explicit stop conditions (no-more-pages, duplicate limit), hard budgets (steps, items, wall-clock), identity-based dedup, and a strict no-blind-retry rule when a fetch returns an ambiguous state. Pure standard library, zero platform APIs — bring your own fetch function.

**Confidence: High (85%)** that budgeted stop conditions + dedup cut the runaway-loop failure mode of scroll automation; **Medium (65%)** that nine named stop reasons cover your provider's failure vocabulary [estimated].

<p align="center"><img src="docs/demo.gif" alt="demo" width="720"></p>

## Problem

"Keep scrolling until you've got everything" is where automation goes feral: the feed re-shows the same ten posts forever, the collector retries a glitched page 500 times, or the loop simply never ends while the operator watches. GUI-automation practice (e.g. mobile-agent work as of 2026-10-11) converged on a safety pattern — bounded attempts, uncertainty pauses, trust only structured tool output — but it lives inside platform-specific toolkits. The pattern itself is platform-free and deserves a 200-line, dependency-free implementation.

- **Why novel:** every failure mode *stops with a named reason* instead of retrying. Ambiguity is a first-class outcome, not an exception to suppress.
- **Overlooked angle:** "uncertain → pause and report" beats "uncertain → retry" because retrying on an untrusted page is how collectors double-scroll, double-collect, and double-act.

## How it works

You supply `fetch(cursor) -> {"items", "has_more", "cursor", "ambiguous"?, "error"?}`. The collector loops with a fixed rule set:

| Stop reason | Trigger | Meaning |
|---|---|---|
| COMPLETE | provider says `has_more: false` | done for real |
| BUDGET_STEPS | max fetches reached | hard cap on page fetches |
| BUDGET_ITEMS | max unique items reached | hard cap on harvest |
| BUDGET_REQUESTS | request-budget circuit breaker tripped | hard cap on requests, independent of steps |
| BUDGET_TOKENS | cumulative token cost reached | cost circuit breaker; the page that tripped it is kept |
| DUP_LIMIT | N consecutive pages with zero new items | feed is looping — the infinite-scroll trap |
| AMBIGUOUS_PAUSE | provider flagged the page uncertain | stop; a human or re-planner decides |
| TIME_BUDGET | wall-clock budget exhausted | latency backstop |
| PROVIDER_ERROR | fetch raised or returned `error` | stop, never retry inside the loop |

Dedup defaults to the item's `id` field when present (feeds re-show entities with mutated metadata), falling back to a canonical structural key. The report always includes the stop reason, counts, elapsed time, collected items, a **cost ledger** (`requests` and `tokens`, with the limits that armed them), and a **checkpoint state** for resuming later.

## How this differs from appium/appium-mcp

appium/appium-mcp (496★ as of 2026-10-11) is the real thing for device control: an MCP server that drives actual Android (UiAutomator2) and iOS (XCUITest) devices and simulators, with AI-powered natural-language element finding via vision models, session create/attach (embedded drivers or remote WebDriver), Java/TestNG test generation from natural language, Page Object Model templates, and a plugin API. It touches phones; this repo never will — there is no device code here at all.

What this repo adds that its README does not offer (its Features list covers platform support, element finding, sessions, test generation, and multilingual interaction — no cost accounting, no resumable harvest):

- **Cost ledger with dual circuit breakers** — appium-mcp exposes automation tools but documents no budget semantics for a long agent-driven collection session. This collector accounts every fetch in the ledger (request count + token cost, provider-reported or a flat default) and trips named stop reasons `BUDGET_REQUESTS` / `BUDGET_TOKENS` when either cap is hit — the page that tripped the breaker is kept, nothing silently continues.
- **Checkpoint/resume snapshots** — nothing in the anchor's docs addresses resuming an interrupted harvest. `save_snapshot` serializes items, seen-keys, cursor, and ledger counters; `resume` continues with a fresh budget and a duplicate-free guarantee across the seam (verified by test: resumed run converges to the identical item set as an uninterrupted one).

Pair them: appium-mcp to drive the screen, this loop to make sure the session above it cannot run away, overspend, or lose its progress.

## Quickstart (~2 min)

```bash
# 1. Self-test: 29 checks, functional / error-path / extreme-edge (~2 s)
python self_test.py

# 2. Demo: five mock provider modes, each stopping with a named reason (+ ledger) (~1 s)
python cli.py demo

# 3. Try the failure modes and the new cost/resume controls
python cli.py collect --mode looping          # -> DUP_LIMIT, exit 1
python cli.py collect --mode ambiguous        # -> AMBIGUOUS_PAUSE
python cli.py collect --mode infinite --max-steps 5 --max-requests 4 --max-tokens 100 --report r.json

# 4. Break a harvest, then resume it from the checkpoint
python cli.py collect --mode clean --total 30 --page-size 8 --max-steps 2 --snapshot snap.json
python cli.py resume snap.json --max-steps 50 # -> COMPLETE, same items, no duplicates
```

## Why not X

| Alternative | Why not |
|---|---|
| Raw `while has_more` loops | No budgets, no dedup, no ambiguity semantics — the runaway case is the default case |
| Airflow / job-framework pagination | Orchestration-grade weight for a 200-line loop; this is embeddable in an agent tool or a script with zero infra |
| Platform SDKs (Appium/WDA, Selenium scroll helpers) | Bind you to one platform and GUI semantics; this accepts any fetch callable, GUI or HTTP or file-based, and ships no iOS/Android code at all |
| Scrapy-style spiders | Built for web crawling at scale with queues and middleware; overkill when the unit of work is "one scroll session with a budget" |

## Minimal Fallback (PLAN B)

No Python? The design is one invariants list: (1) cap fetches, (2) cap items, (3) stop after N identical pages, (4) never retry an ambiguous page, (5) dedup on a stable key. Any language expresses this in ~50 lines; the stop-reason vocabulary above is the contract to preserve.

## Design Trade-offs

Priority order: **stopping safely > harvesting completely > throughput**. Ambiguous pages discard only that page (earlier items are kept) and never auto-retry — this trades maximum recall for the guarantee that the collector never acts on untrusted state. DUP_LIMIT defaults to 3 consecutive no-new-item pages, tolerant of feeds that re-show a couple of entries per page (realistic) but intolerant of true loops. Dedup prefers the `id` field, so an item whose text mutates between pages counts once — if your feed genuinely emits distinct entities sharing an id, you must supply a richer key.

## Limits & Second-order Effects

- If teams adopt "pause on ambiguity" widely, they inherit a human-review queue; budget for it or the pauses pile up unread.
- Strict budgets can make partial harvests look like success (`BUDGET_ITEMS` with 99% of data); downstream consumers must treat the stop reason, not just the item list, as the result's meaning.
- id-based dedup fails silently if a provider reuses ids across distinct entities — supply a custom key and test it.
- The nine stop reasons become a shared vocabulary; renaming or adding one is an API change for every report consumer.
- Token ledger trusts the provider's reported cost (or the flat default) — a provider under-reporting tokens under-arms the breaker; treat the ledger as self-reported telemetry.
- Resume restores cursor and seen-keys, not provider-side state: mock-style providers whose behavior depends on call count (glitch positions) restart their counters on resume.

## FAQ

**Does this scrape or drive a GUI?** No. It is the loop and its safety rules only. You provide `fetch` — an HTTP paginator, a screen-reader feed, a file iterator. Nothing here touches iOS, Android, or any private API.

**Why not auto-retry ambiguous pages once?** Because "ambiguous" means the provider cannot vouch for page state; one retry on the same untrusted page is how double-scrolls happen. The design hands uncertainty upward instead.

**When NOT to use this?** Don't use it for well-behaved HTTP APIs with real cursor pagination and no repeats — a plain loop is simpler there. Don't use it for *distributed* collection across machines (the checkpoint is single-session resume, not a shared queue). And don't use it as a rate limiter — it budgets *attempts and cost*, not politeness.

**What does the caller do after AMBIGUOUS_PAUSE?** Anything except blind continuation: settle the view, re-plan, or ask a human. The report's `pages_fetched` and `item_count` tell you exactly where to resume from.

## [Core Assumptions]

1. A provider can flag its own uncertain pages (`ambiguous: true`) — if it can't, AMBIGUOUS_PAUSE never fires and this design degrades to budgets-only.
2. Items are identifiable by a stable key (`id` or a caller-supplied function); without stable identity, dedup and DUP_LIMIT lose their meaning.
3. A partial harvest with a named stop reason is more valuable than a complete harvest with unbounded runtime.
4. Retrying inside the collector is always wrong; retries belong to a layer that can re-plan, not the tight loop.

*Data as of 2026-10-11. Measured: 29/29 self-test checks (~2 s), the five-mode demo, and the snapshot→resume parity test (identical item sets, zero duplicates), repro via `python self_test.py` / `python cli.py demo` on Windows 10 / CPython 3.11. Anchor facts (appium-mcp features) from its README as of this date. Coverage claims about provider failure vocabularies [estimated].*
