# Alignment Audit (Rules 85-100 / 16 items) — bounded-scroll-collect

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Defensive automation-safety tool; no platform private APIs, no attack surface; Limits section covers misuse of partial harvests. |
| 2 | Privacy/keys | PASS | No keys/tokens/real names; synthetic feed items only. |
| 3 | Copyright boundary | PASS | Pattern inspiration only, zero copied text; no iOS/Appium code imported or named beyond one contextual mention; MIT LICENSE present. |
| 4 | Fact-check numbers | PASS | 29/29 checks + five-mode demo + resume-parity test measured, repro commands given; failure-vocabulary coverage marked [estimated]; anchor facts dated as-of. |
| 5 | Confidence grading | PASS | README: High (85%) and Medium (65%) [estimated] labels with basis. |
| 6 | Minimal Fallback | PASS | "Minimal Fallback (PLAN B)": five-invariants list, ~50 lines in any language. |
| 7 | Quickstart timing | PASS | Quickstart labelled ~2 min, staged (self-test → demo → failure modes → snapshot/resume). |
| 8 | Conflict arbitration | PASS | "Design Trade-offs": stopping safely > harvesting completely > throughput, with ambiguity trade-off explained. |
| 9 | Changelog ≥2 iterations | PASS | CHANGELOG v0.1.0 → v0.1.1 → v0.1.2; v0.1.2 adds anchor-differentiation features (cost ledger, checkpoint/resume). |
| 10 | Exemption (session rule) | N/A | Session-level governance item; static repo not applicable. |
| 11 | Knowledge cutoff | PASS | Mobile-agent practice and appium-mcp facts referenced "as of 2026-10-11"; README footer repeats the date. |
| 12 | Explicit assumptions | PASS | `[Core Assumptions]` lists 4 premises (ambiguity flaggability, stable identity, partial-harvest value, no in-loop retries). |
| 13 | Three-part self-test | PASS | functional (13) + error paths (7) + extreme edges (9) = 29/29 PASS. |
| 14 | Socratic FAQ | PASS | "When NOT to use this?" — well-behaved APIs, distributed (not single-session) resumable needs, rate limiting. |
| 15 | Pareto iteration | PASS | Round 2: 15→21 tests (+40%), three real bugs fixed. Round 3 (v0.1.2): 21→29 tests (+38%) + two new capabilities; CHANGELOG-traceable. |
| 16 | ≤60-word opening | PASS | First paragraph is 55 words with a judgment sentence ("bring your own fetch function"). |

Additional: **Second-order effects** — "Limits & Second-order Effects" covers human-review queues, partial-harvest false success, id-collision blind spot, and stop-reason vocabulary lock-in.
