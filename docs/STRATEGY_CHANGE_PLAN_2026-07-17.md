# Strategy Correction, OTM Research, Rotation, and Visibility Plan

**Goal:** Deliver a PAPER-safe strategy runtime before the 2026-07-17 market open that preserves the approved ATM/ITM cross universe, adds a bounded OTM research exception, restores global rotation analysis, prevents reservation deadlock, and makes every index/capital/rejection decision visible.

**Architecture:** Keep one serialized engine and one active position. Market data remains one combined five-index quote batch. While flat, selected indices compete for entry every completed-candle scan; while active, the same scans are diagnostic/rotation-only and can atomically replace—but never overlap—the active position.

**Publication:** Local changes and verification only. Do not stage, commit, push, merge, or modify GitHub.

## Global constraints

- PAPER must never invoke broker write methods.
- Preserve `config.json` backtest dates exactly.
- Retain all current ATM/ITM pairs and existing safety/economic gates.
- NIFTY/BANKNIFTY/FINNIFTY are PAPER tradable; MIDCPNIFTY/NIFTYNXT50 are observe-only.
- One active or reserved position globally.
- One-second risk/exit checks remain higher priority than rotation scanning.
- Entry/rotation signals use completed synchronized candles.
- No requirement may be removed unless the change-impact section explicitly says so.

## Change impact contract

### Retained

- Current 25 ATM/ITM cross pairs, or 16 ITM×ITM pairs on SIDEWAYS expiry.
- Dual-decay, ratio 2.5, spread/integrity, stale/asynchronous data, capital, projected-net, return, slippage, final-validation and cutoff gates.
- Dynamic equal quantities on CE and PE.

### Added

- PAPER-only CE OTM1–OTM2 × PE OTM1–OTM2: four research pairs per tradable index.
- SIDEWAYS guarded divergence buffer: 0.75–1.0% and 5.0–6.0%.
- Per-index Top 5/10, scan funnel, capital affordability, and global winner/runner-up visibility.
- Global selected-index rotation analysis while one position remains under one-second risk monitoring.

### Modified/replaced

- Blanket both-OTM rejection becomes a narrow guard-approved PAPER exception; LIVE remains blocked.
- Fixed ₹103 rotation floor becomes cost-aware net economics.
- Same-index-only rotation comparison becomes selected tradable-index comparison.
- Global first-N diagnostic slice becomes Top N per index per scan cycle.

### Removed

- No ATM/ITM entry is removed.
- Remove only broken legacy dependencies: NIFTY cache/lot assumptions in rotation and stale global diagnostic truncation.

## Exact strategy rules

### Divergence

- SIDEWAYS normal zone: 1.0–5.0% with existing configured economics.
- SIDEWAYS buffer zone: 0.75–1.0% inclusive at the lower edge and 5.0–6.0% inclusive at the upper edge; require projected net ≥ ₹200 and projected return ≥ 0.50%.
- SIDEWAYS outside 0.75–6.0%: reject.
- Confirmed DIRECTIONAL: retain 1.0–10.0%; an 8% candidate remains directional-only.

### OTM research

- PAPER only; never executable in LIVE.
- Confirmed DIRECTIONAL only; winning leg must align with spot direction.
- Only four pairs: CE OTM1/OTM2 crossed with PE OTM1/OTM2.
- Minimum executable ask ₹15 on each leg.
- Expiry day cutoff 12:00 IST; reject at or after 12:00.
- Retain ratio 2.5, dual-decay, spread, synchronized-candle, projected-net, return, capital, price-integrity and final-validation gates.
- Tag diagnostics/plans/trades as `OTM_RESEARCH`; established pairs are `ATM_ITM`.
- Do not implement IV-percentile gating until synchronized live IV exists.

### Rotation

- Scan selected indices every 60 seconds/latest completed candle while active, after the one-second risk/exit check finds no immediate exit.
- Never enqueue a second ENTRY while active; only a serialized ROTATION signal may replace it.
- Current close economics use `active_trade.net_pnl` and index-correct costs.
- Require active net P&L ≥ ₹100 after costs.
- Replacement must pass every normal entry gate and exceed the active pair's projected hold net by at least ₹100.
- Preserve cooldown and entry cutoff.
- Keep reservation ACTIVE through confirmed close→replacement; if replacement fails, remain flat and release reservation.
- Successful normal exit always releases reservation.

## Task 1 — Reservation lifecycle (root)

- Add a failing regression proving successful `EXIT_BOTH` changes reservation from ACTIVE to EMPTY and permits a second reservation.
- Add failure-path tests for stale exit, close exception, and already-flat exit.
- Implement release only after confirmed successful close/persistence; do not release on a stale signal aimed at another trade.

## Task 2 — Bounded OTM and divergence buffer

- Add failing pair-template tests: existing 25 unchanged; four OTM research pairs added only when enabled.
- Add failing signal/ranker tests for 0.74 reject, 0.75 guarded, 0.99 guarded, 1.0 normal, 5.0 normal, 5.01 guarded, 6.0 guarded, 6.01 SIDEWAYS reject, and 8.0 DIRECTIONAL pass.
- Add OTM guard tests for PAPER/LIVE, direction, ₹15 floor, OTM depth, dual decay, ratio, expiry 11:59/12:00, projected net and stale data.
- Implement pure guard/configuration without weakening established pair rules.

## Task 3 — Fair diagnostics and capital model

- Add failing tests proving Top N is retained independently for every index regardless of scan order.
- Add cycle ID, pair class, spot, ATM, moneyness, generated/quotable/signal/economic/final counts, and prefilter rejection reasons.
- Add a pure capital-affordability view: combined ask, lot size, one-lot premium, deployable capital, max lots, charges estimate, shortfall and quote age.
- Keep full CSV/JSON fidelity with a bounded per-index history.

## Task 4 — Index-aware global rotation (root)

- Add failing BANKNIFTY/FINNIFTY tests that prove rotation uses the active/candidate index cache and lot size.
- Add failing integration test: active NIFTY, better FINNIFTY candidate, net/cost thresholds pass, one ROTATION enqueued.
- Add keep-current tests for active net below ₹100, improvement below ₹100, cooldown, cutoff, observe-only winner and immediate risk exit.
- Refactor rotation inputs away from the global NIFTY cache.
- Reuse multi-index scan results in rotation-only mode without allowing coordinator ENTRY dispatch.

## Task 5 — Strategy monitoring UI

- Component tests first.
- Per-index tabs/cards: Top 5/10 pairs, 5×5 established matrix plus four OTM research cells, funnel counts and reasons.
- Capital cards: spot, ATM, expiry, lot, combined premium, one-lot cost, deployable equity, max lots, charges, shortfall and maximum premium-at-risk.
- Global comparison: best candidate per tradable index, winner, runner-up and displacement reason.
- Fixed 14–20 visible columns; details drawer for overflow; no dynamic column explosion.

## Verification gate

- Focused red→green evidence for every task.
- Full Python test suite with isolated `--basetemp`.
- Frontend component suite and production build.
- `git diff --check`.
- Re-read PAPER/LIVE settings, broker executor diff, config dates and changed-file scope.
- Runtime fixture proves: three tradable indices compared, per-index Top N visible, cross/OTM classifications visible, second entry possible after exit, and zero broker writes.

## Verified implementation status (2026-07-17)

- Task 1: successful normal PAPER exit releases the global reservation; regression covered.
- Task 2: established 25/16 ATM-ITM templates retained; bounded four-pair PAPER OTM research and guarded SIDEWAYS divergence buffers implemented.
- Task 3: fair per-index/per-cycle Top N, full bounded exports, funnel/moneyness fields and capital affordability implemented and wired into scanner diagnostics.
- Task 4: active-position replacement discovery scans every selected index without dispatching ENTRY, uses active-index cache/lot economics, and enqueues only serialized ROTATION.
- Task 5: fixed 14-column inspector, per-index Top 5/10, matrix, funnel, affordability, global comparison and details drawer implemented.
- Full Python verification: 233 passed, one third-party Starlette deprecation warning.
- Frontend verification: 11 tests passed and production Vite build passed.
- No Git stage, commit, push or broker order was performed.
