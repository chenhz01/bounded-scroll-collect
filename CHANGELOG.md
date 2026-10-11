# Changelog

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
