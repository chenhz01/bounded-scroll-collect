# Changelog

## [0.1.2] - 2026-10-11

### Added (anchor differentiation: appium/appium-mcp re-audit)

- **Cost ledger with dual circuit breakers** (`CollectorConfig.max_requests` / `max_tokens` / `default_page_tokens`, report `ledger`, stop reasons `BUDGET_REQUESTS` / `BUDGET_TOKENS`): every fetch is accounted (request count + token cost, provider-reported or flat default) and either cap trips a named stop reason; the page that tripped the token breaker is kept. appium-mcp's README documents no cost/budget semantics for agent-driven sessions.
- **Checkpoint/resume snapshots** (`save_snapshot` / `resume`, CLI `collect --snapshot` / `resume`): items, seen-keys, cursor, and ledger counters serialize to JSON; resuming with a fresh budget converges to the identical item set as an uninterrupted run with zero duplicates across the seam (test-verified). Resolves the v0.1.1 FAQ's stated "no checkpointing here" limitation for the single-session case.
- Dedup keys are now stored as canonical strings (behavior-neutral, snapshot-serializable).
- 8 new self-test cases (21 → 29): request/token breakers, default-token ledger, resume parity, corrupt-snapshot ValueError, max_requests validation, breaker-fires-but-page-kept, two-break resume chain.
- FAQ and stop-reason table updated (seven → nine reasons); Limits gains token self-reporting and provider-side-state caveats.

## [0.1.1] - 2026-10-11

### Changed (round-2 iteration after 16-item self-audit)

- **Correctness (real bug):** the expanded suite caught that the default dedup key hashed the *whole item dict* — a re-shown item with mutated metadata (same id, new text) escaped dedup entirely and a test run harvested duplicates. Default key now prefers the `id` field; added a regression test proving zero duplicate ids under 40% re-show traffic.
- **Correctness (mock fidelity):** two mock-provider bugs — the "clean" mode's dup injection silently *dropped* new items (feed lost 2 of 25), and the "looping" mode leaked one new item per page so it never tripped DUP_LIMIT and even terminated on its own. Both mocks now behave like real feeds; "looping" re-emits the first page forever.
- **Correctness (+~25% test rigor):** three test expectations were wrong (step-budget case dup-limited first; max_dups=1 off-by-one on pages; time-budget case hit the item cap first). Suite grew from 15 to 21 checks, all PASS.

## [0.1.0] - 2026-10-11

### Added

- `collector.py`: bounded collection loop with seven named stop reasons (COMPLETE, BUDGET_STEPS, BUDGET_ITEMS, DUP_LIMIT, AMBIGUOUS_PAUSE, TIME_BUDGET, PROVIDER_ERROR), no-blind-retry rule, config validation, id-first dedup with canonical structural fallback, and a five-mode mock `ScrollProvider` (clean / looping / ambiguous / infinite / crashy).
- `cli.py`: `collect` (mode/budgets/report) and `demo` subcommands; exit 0 only on COMPLETE.
- `self_test.py`: three families — functional (9), error paths (5), extreme edges (7: single-step budget, 100KB items, 0.05 s time budget, unicode keys, partial harvests).
- MIT LICENSE (zhengming contributors), README, initial ALIGNMENT audit.
