# Codex Handover: AutoTrader Safety, Price Integrity, Capital, Diagnostics, and Multi-Index Design

**Conversation dates covered:** 2026-07-14 and 2026-07-15 (Asia/Calcutta)
**Last updated:** 2026-07-15, during the Streamlit-replacement and runtime index-selection design discussion
**Workspace:** `C:\Users\LENOVO\Documents\chatgpt_auto_trader`
**Current branch:** `codex/capital-live-safety-readiness-docs`
**Current branch commit:** `a2e516d Add capital controls, live safety gates, and system documentation`
**Purpose:** Give another AI or engineer enough context to continue safely without relying on the original conversation.

## 1. Non-negotiable user instructions

1. PAPER mode is fully simulated and must never submit a real Dhan/broker order.
2. Tests must never submit real broker orders.
3. LIVE execution must use only the amount explicitly allocated in the UI, even when the Dhan account contains more money.
4. LIVE must not consume unallocated Dhan funds because of a sizing, retry, partial-fill, restart, or concurrency defect.
5. Capital/allocation changes require the engine to be stopped and no open position.
6. Do not add an account-wide Dhan emergency kill-switch button at this stage.
7. Preserve the user's `config.json` backtest dates:
   - `backtest_from_date`: `2026-06-09`
   - `backtest_to_date`: `2026-07-13`
8. Preserve user-owned/unrelated working-tree changes. The current uncommitted `config.json` change is only newline-at-EOF state; do not overwrite it.
9. Do not create or commit unrelated observer/workflow files.
10. New features must be separated into focused modules. Do not continue placing strategy, database, execution, and presentation logic in one large UI file.
11. Do not claim a fix is complete after inspection alone. Test expected behavior, failure paths, restart behavior, UI behavior, and PAPER/LIVE separation.
12. The user does not want to spend market hours discovering preventable defects. Code-level and UI-level validation must be completed before handoff.
13. No new trading code is authorized in the current design phase. The user explicitly said, “don't write the code yet.”
14. This handover must be updated after every assistant response in this task.

## 2. Git and verification history

### 2026-07-14 safety and price-integrity commit

- Earlier commit `2e96597 Harden paper execution and correct option transaction costs` was pushed through branch `codex/safety-price-integrity-paper-sl` and merged into `main` as merge commit `b742289`.
- Test result reported by the user before that merge: `43 passed, 2 warnings`.
- One warning was SQLAlchemy's `declarative_base()` deprecation.
- One warning was a Windows `.pytest_cache` creation issue; it did not fail the tests.

### 2026-07-14 capital/live-safety/readiness commit

- Branch: `codex/capital-live-safety-readiness-docs`
- Commit: `a2e516d Add capital controls, live safety gates, and system documentation`
- Push succeeded and the local branch tracks `origin/codex/capital-live-safety-readiness-docs`.
- Test result reported immediately before commit/push: `90 passed, 1 warning in 4.55s`.
- The remaining warning was the Windows pytest cache warning.
- Commit scope: 41 files, 3,282 insertions, 177 deletions.
- Important new files:
  - `database/capital_ledger.py`
  - `execution/capital_firewall.py`
  - `strategy/live_readiness.py`
  - `tests/test_broker_executor_safety.py`
  - `tests/test_capital_ledger.py`
  - `tests/test_critical_findings_regression.py`
  - `tests/test_live_capital_firewall.py`
  - `tests/test_live_readiness.py`
  - `docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md`
- The branch push succeeded. Pull-request creation/merge status is not confirmed in this conversation.

## 3. 2026-07-14 chronology, issues, decisions, and implemented work

### 3.1 Low option entries and incorrect transaction costs

Observed:

- PAPER entered CE around ₹1.95 and PE around ₹1.90.
- The journal displayed transaction costs around ₹2,678 for a trade with gross P&L around ₹253.50.
- The UI initially hid the effective position quantity, causing the trade to appear like a one-lot trade.
- The actual dynamic quantity could be 179 lots or more because cheap premiums allowed many lots under the capital-only formula.

User decisions:

- Keep dynamic quantities based on available capital.
- Both CE and PE must always use the same number of lots.
- Display both `Lots` and `Units / Leg` prominently in active-position cards and the journal.
- Replace the invalid fixed `₹103 × lots` transaction-cost calculation with Dhan order/turnover-based charges.

Implemented direction:

- Added `core/transaction_costs.py`.
- Cost calculation uses four option orders for a paired round trip: CE buy, PE buy, CE sell, PE sell.
- Brokerage is order-based, while exchange charges, STT, SEBI fees, stamp duty, and GST use turnover/tax bases.
- PAPER entry prices use executable-side prices rather than inventing fills from stale LTP values.
- Quantity became visible in active-position cards and journal.

### 3.2 UI journal compatibility defect

Observed:

- Streamlit raised `AttributeError: 'Trade' object has no attribute 'units_per_leg'` in `ui/app.py`.

Cause/direction:

- UI assumed a model attribute that older/current `Trade` objects did not expose.
- Quantity display was moved toward a compatibility helper (`units_per_leg(trade)`) based on `quantity × lot_size`, rather than directly reading a missing attribute.

### 3.3 PAPER daily stop behavior

Original behavior:

- The daily circuit breaker blocked new PAPER entries once cumulative loss exceeded 3% of ₹45,000 (₹1,350).
- Console repeatedly logged `Daily Circuit Breaker is active. Entries blocked.`

User decision:

- LIVE: stop accepting new trades after the daily loss threshold.
- PAPER: square off according to the same hard per-trade/risk exit rules, but continue looking for later test opportunities after the daily threshold.
- Trades opened after PAPER crosses the daily threshold must be tagged with `SL`/`-SL` so normal and post-threshold trades can be separated.
- Per-trade risk must be recalculated from remaining equity, not always from the original ₹45,000.

Example:

- Initial equity ₹45,000, 3% risk = ₹1,350.
- After losing ₹1,350, remaining equity = ₹43,650.
- Next trade's 3% hard loss amount = ₹1,309.50.

Implemented direction:

- PAPER continues entries after the daily threshold and tags them `-SL`.
- LIVE retains a daily stop latch.
- `risk_capital_at_entry` and `hard_stop_loss` are persisted with trades.
- Exit managers use the equity/risk captured at entry.

### 3.4 Expiry-day dual-decay loss and uncapped cheap-premium sizing

Observed:

- On expiry/near-expiry conditions, both selected CE and PE premiums decayed.
- A PAPER position reached roughly 247 lots / 16,055 units per leg and around ₹15,252 active loss.
- Both options were very cheap and far from useful ATM exposure.
- The position did not exit as early as the user expected.

Confirmed concerns:

- Cheap premium plus capital-only sizing can create extreme lot counts.
- Calling the “less negative” option the winner is invalid when both legs are losing.
- Both-OTM paired buying is especially dangerous during theta/IV decay.
- A regime/expiry guard and a hard units ceiling are needed in addition to capital sizing.

Implemented direction:

- `max_units_per_leg = 1800` temporary NIFTY safety ceiling.
- `max_capital_deployment_pct = 0.90` to reserve cash for costs/slippage.
- Reject candidates where both CE and PE velocities are non-positive.
- Reject dangerous both-OTM CE/PE combinations.
- Near-expiry guard:
  - disable SIDEWAYS paired buying near expiry;
  - restrict directional candidates to ATM/near-ATM.
- Apply hard per-trade loss protection based on entry equity.

### 3.5 Claude critical-findings regression tests

The user supplied `test_critical_findings_regression.py` and an audit summary. The four findings were directionally valid:

1. Candidate generation freely formed the CE × PE Cartesian product across ATM ±10 strikes without enforcing matched strikes, ATM, or moneyness.
2. SIDEWAYS evaluation could accept both-negative option velocities and call the less-negative leg the winner.
3. Pair ranking could select negative projected-net opportunities because it sorted without enforcing positive net return.
4. Per-trade stop and uncapped sizing behavior required explicit regression coverage.

The pre-existing test `test_position_sizer_keeps_quantity_dynamic_for_low_premium_pair` had asserted 179 lots as correct behavior, so it needed revision when the safety ceiling was introduced.

Implemented direction:

- Added the supplied critical regression test file to the repository.
- Updated position-sizing expectations to honor the hard units ceiling.
- Added/expanded regression tests around negative projected profit, both-negative velocities, hard loss exits, and quantity safety.

### 3.6 PAPER equity adjustment and LIVE allocation

User requirement:

- PAPER must allow a refill/deposit/withdrawal-style adjustment while keeping trading P&L separate.
- PAPER adjustments must be recorded as transactions, not silently overwrite losses.
- LIVE must not initiate broker fund transfers.
- LIVE may synchronize/confirm broker balance, but the strategy may use only the UI allocation.
- Example: if Dhan has ₹100,000 and the UI allocation is ₹40,000, the application must never use the other ₹60,000.
- Allocation is not permanently fixed at ₹40,000; whatever the user sets for the stopped session becomes the limit.
- Capital changes are allowed only when the engine is stopped and no position is open.

Implemented direction:

- Append-only capital ledger with transaction types including deposit, withdrawal, trade P&L, allocation change, and broker balance sync.
- PAPER target-equity adjustment records the difference as deposit or withdrawal.
- LIVE allocation must be positive and cannot exceed broker-confirmed funds.
- Session allocation is captured at engine start.
- `LiveCapitalFirewall` limits deployment to the allocated amount and reserve percentage.
- LIVE readiness checks and explicit `live_trading_enabled = false` gate remain in place.
- No application-driven Dhan fund transfer feature was added.

### 3.7 Documentation requested on 2026-07-14

The user requested comprehensive architecture and requirements documentation covering architecture, pair selection, old versus current requirements, execution steps, and strategies.

Implemented:

- `docs/SYSTEM_EVOLUTION_AND_CURRENT_ARCHITECTURE_2026-07-13_TO_2026-07-14.md`
- README/CHANGELOG/legacy requirements were updated or linked.
- That document explicitly identified an unresolved live-regime defect: the engine was using spot as VWAP/high/low and constant ATR `2.0`, making live regime classification unreliable.

## 4. 2026-07-15 chronology, observed failures, and confirmed root causes

### 4.1 No trades for roughly one hour

Runtime evidence from approximately 09:30–10:14:

- Every two minutes the engine generated 289 or 324 Cartesian pairs.
- Liquidity filter reported all pairs passing.
- Entry signal reported `0 of 289` or `0 of 324` passing.
- Engine repeatedly logged `No scanned pairs met entry signals.`
- Regime was always displayed as `SIDEWAYS (SIDEWAYS)` even during a clearly upward spot move.
- One scan was skipped because memory usage exceeded 95%.
- Intermittent cycles failed with `Expecting value: line 1 column 1 (char 0)`.

Confirmed root cause 1 — regime inputs are placeholders:

- `ui/app.py` appends the same spot value to closes, highs, lows, and VWAP.
- ATR is always appended as `2.0`.
- Directional classification requires real VWAP relationship, high/low structure, and expanding ATR.
- Therefore the live engine is effectively forced into SIDEWAYS or otherwise produces unreliable regimes.

Confirmed root cause 2 — option velocity is not previous-candle velocity:

- `strategy/divergence_scanner.py` calculates `(last - open) / open`.
- The `open` originates from the option-chain/session data, not necessarily the prior completed candle.
- The intended strategy requires the latest completed candle close compared with the previous completed candle close.

Confirmed root cause 3 — reasons are discarded:

- `EntrySignal.evaluate_signals()` returns only survivors.
- Rejected pairs retain no stage or reason.
- The activity message cannot distinguish signal rejection from later ranker rejection.

Confirmed root cause 4 — cumulative P&L is mislabeled and reused as daily P&L:

- Recovery loads cumulative realized P&L into `engine_inst.realized_pnl`.
- UI labels that value `Realized P&L` and `Total Day P&L` without filtering by date.
- Daily circuit-breaker logic also uses that cumulative number.
- Consequently yesterday's loss caused today's PAPER threshold to be shown as active before any new trade.

Confirmed root cause 5 — malformed/empty market-data response handling:

- `Expecting value: line 1 column 1` is consistent with JSON decoding an empty or non-JSON response.
- The current top-level loop logs only the exception text.
- Required: identify endpoint/component, status code, response content type/length, bounded sanitized preview, retry/backoff, stale-data blocking, and a clear UI health state. Never trade using fabricated or stale fallback prices.

### 4.2 Exact current entry pipeline

Current flow:

1. Generate all CE × PE strike combinations inside ATM ± configured range.
2. Filter CE and PE strikes independently for liquidity.
3. Rebuild the Cartesian product.
4. Compute CE/PE velocities from option `open` to current `last/close`.
5. Reject both-negative velocities.
6. Reject a particular both-OTM layout (`CE strike > spot` and `PE strike < spot`).
7. Require divergence inside the configured band (currently 1–5%).
8. In DIRECTIONAL mode, require winning-leg alignment with spot direction.
9. Rank survivors using executable asks, premium similarity, expected combined movement, estimated charges/slippage, confidence, volume, OI, and spread.
10. Size and validate the selected pair.

Misleading behavior:

- If entry survivors exist but the ranker rejects all of them, UI still logs `No scanned pairs met entry signals.`

### 4.3 10:07 NIFTY example and divergence profitability

Screenshot example around 24200 ATM:

- CE candle: open ₹146.75, close ₹151.80, shown change +3.23%.
- PE candle: open ₹166.05, close ₹161.75, shown change −2.32%.
- Approximate divergence: `|3.23 - (-2.32)| = 5.55%`.
- Under the old universal 1–5% band, this would fail because 5.55% is above 5%.
- CE/PE premiums were similar and the CE was directionally aligned with an upward spot move.
- Buying both legs from the displayed candle opens would produce only about ₹0.75 combined gain per unit, or ₹48.75 gross for 65 units, before four-order charges.
- The current ranker's illustrative projection was around ₹86.54 gross per lot versus approximately ₹152 of one-lot costs/slippage, producing a negative projected result.

Important principle:

- Divergence is the absolute difference between signed leg percentage moves.
- Profit depends on the signed, premium-weighted sum of both leg moves after executable prices, transaction charges, and slippage.
- A large divergence can still lose if the losing leg cancels the winner.

Illustrative ₹150-per-leg, 65-unit examples with about ₹152 one-lot costs/slippage:

| CE move | PE move | Divergence | Approx. gross | Approx. net | Outcome |
|---:|---:|---:|---:|---:|---|
| +3% | +1% | 2% | ₹390 | ₹238 | profitable 1–5% case |
| +4% | −1% | 5% | ₹292.50 | ₹140.50 | profitable 1–5% case |
| +2.5% | −1.5% | 4% | ₹97.50 | −₹54.50 | losing 1–5% case |
| +6% | −1% | 7% | ₹487.50 | ₹335.50 | profitable 5–10% case |
| +5% | −3% | 8% | ₹195 | ₹43 | weak profitable 5–10% case |
| +5% | −4% | 9% | ₹97.50 | −₹54.50 | losing 5–10% case |

Additional design defect identified:

- The ranker evaluates one-lot profitability before dynamic sizing.
- Dhan option brokerage is per executed order, while several other charges scale with turnover.
- Exact quantity, order slicing/freeze limits, and scalable slippage must be known before final projected-net validation.
- Do not use larger size merely to rescue an otherwise weak edge; require a safety buffer and validate fills/slippage in PAPER.

## 5. Approved 2026-07-15 strategy and timing decisions

The user approved all of the following:

1. Entry evaluation runs every 60 seconds.
2. Active-position risk and exit monitoring continues every 1 second.
3. Entry signals use completed candles only.
4. A completed candle is evaluated once; repeated 60-second scans must not duplicate the same candle signal.
5. Divergence uses latest completed close versus previous completed close, not session open versus current LTP.
6. SIDEWAYS divergence band: 1–5%.
7. Confirmed DIRECTIONAL divergence band: 1–10%.
8. High divergence alone is never an entry reason; projected net, direction, spreads, liquidity, moneyness, expiry, and risk validation still apply.
9. Scan five NSE option indices:
   - NIFTY
   - BANKNIFTY
   - FINNIFTY
   - MIDCPNIFTY
   - NIFTYNXT50
10. NIFTY, BANKNIFTY, and FINNIFTY may compete for entry in the first version.
11. MIDCPNIFTY and NIFTYNXT50 remain observe-only until PAPER evidence proves readiness.
12. Permit only one globally active trade across all indices in the first version.
13. Continue scanning/diagnosing observe-only indices, but do not submit entries for them.
14. PAPER remains fully simulated.

## 6. Approved modular multi-index architecture

The user approved the following high-level flow:

1. A 60-second scan trigger obtains latest completed candles.
2. Each selected index is evaluated independently.
3. Observe-only indices generate diagnostics but are ineligible for execution.
4. Each tradable index produces its best eligible candidate.
5. A global selector compares candidates across tradable indices.
6. An atomic global position guard confirms no active/reserved position.
7. Safe quantity is calculated using current PAPER equity or LIVE allocation.
8. Exact quantity-aware costs, order slicing, and slippage are calculated.
9. Final validation reruns immediately before execution.
10. PAPER executor simulates the selected trade.
11. Exit/risk monitoring continues every second.

Required focused modules (names are design-level and may be refined before implementation):

- Index registry: symbols, lot sizes, strike steps, expiries, freeze limits, trading/observe status, liquidity rules.
- Completed-candle store/service: per-index spot and option closed candles with timestamp alignment.
- Market-feature calculator: real VWAP, OHLC structure, ATR, regime, and direction.
- Explainable pair evaluator: structured pass/fail stages and reasons.
- Multi-index scanner: independent index evaluations.
- Global candidate selector: risk-adjusted comparison across indices.
- Global position guard/reservation: one atomic active-or-pending position.
- Quantity-aware profitability calculator: exact expected gross, charges, slippage, and safety buffer.
- Scan-capture service: opt-in diagnostics collection and export.
- Period P&L service: Today/Week/Month/Year/All-time using timestamps and execution mode.
- Dedicated live-monitoring UI component/client.
- Existing PAPER/LIVE execution separation and LIVE safety gates.

## 7. Requested rejection-inspector behavior

The user requested a widget under Engine Activity Console with:

- Manual Start and Stop capture controls.
- No collection before Start.
- Capture only scans performed after enablement.
- Top 5 or Top 10 option.
- Include both passed and failed pair-selection outcomes.
- Show exact rejection stage and one or multiple reasons.
- Include index, expiry, strikes, CE/PE prior close, latest close, velocities, divergence, regime, spread, liquidity, projected gross, estimated costs, projected net, confidence, status, scan/candle timestamp.
- Download captured data, initially CSV; structured JSON may also be useful for AI debugging.
- A bounded in-memory buffer and/or session-specific persisted diagnostic file so the feature cannot exhaust memory.
- Diagnostics must be observational only and must not change candidate selection.

Required stage labels:

`GENERATED → LIQUIDITY → CANDLE_DATA → SIGNAL → RANKING → GLOBAL_SELECTION → EXECUTION_VALIDATION`

Every stage must produce `PASS`, `FAIL`, or `NOT_EVALUATED`, with reasons.

## 8. Requested period P&L behavior

The live operational view must support:

- Today
- Current week
- Current month
- Current year
- All time

Requirements:

- Realized P&L is filtered by closed trade exit timestamp.
- Active-position P&L is shown separately and only belongs in current total/open exposure.
- PAPER and LIVE results must never be silently combined.
- Capital deposits/withdrawals/allocation changes are not trading P&L.
- Daily circuit breaker uses today's realized P&L plus current active unrealized P&L, not cumulative historical P&L.
- New trading day resets the daily threshold calculation automatically without deleting history.
- LIVE daily-stop latch remains keyed by actual trading date.
- Timezone boundaries use Asia/Calcutta/IST consistently.

## 9. Runtime index-selection feature added on 2026-07-15

New user requirement:

- UI must display checkbox-style index selection.
- User may select one, multiple, or All.
- Default is All.
- Runtime changes must be respected while the engine is running.
- The engine must then look for trades only in the selected universe.

Safe design semantics:

1. Selection changes affect new scans/entries beginning with the next scan snapshot.
2. A currently active position continues to receive 1-second risk and exit monitoring even if its index is deselected.
3. Deselecting an index must never abandon or auto-close an active position unless the user separately requests a valid manual exit.
4. Each scan takes an immutable versioned snapshot of selected indices, preventing mid-scan mutation.
5. `All` selects all five supported indices; observe-only/tradable permissions still apply.
6. If only an observe-only index is selected, scans and diagnostics run, but the UI clearly states that entries are disabled for that index.
7. Zero selected indices must be rejected or represented as an explicit `Pause new entries` state, not interpreted ambiguously.
8. Selection changes are audit-logged with timestamp, previous set, new set, and execution mode.
9. LIVE/PAPER selection must never bypass one-position, capital, daily-stop, readiness, expiry, or broker validation gates.

## 10. Streamlit replacement discussion started on 2026-07-15

User question:

- Can a new UI application be created so the system no longer depends on Streamlit, and would that improve performance/other aspects?

Preliminary answer/design direction:

- Yes. A separate web UI can improve isolation, real-time updates, testability, responsiveness, and maintainability.
- The biggest improvement is architectural separation, not merely changing visual frameworks.
- Current Streamlit concerns include full-script reruns, UI/engine shared process state, `missing ScriptRunContext` background-thread warnings, repeated initialization, and a large `ui/app.py` containing orchestration and presentation.
- Recommended target:
  - Python trading-engine service independent of any UI.
  - FastAPI control/read API.
  - WebSocket or Server-Sent Events for live logs, metrics, positions, scan diagnostics, and health.
  - React + TypeScript (for example Vite) client for responsive UI and component-level testing.
  - SQLite can remain initially behind repository/service interfaces; migration to a server DB is not required for the first local single-user version.
- Recommended migration is phased and PAPER-only until parity is proven:
  1. Extract engine/control interfaces while keeping Streamlit operational.
  2. Build new UI beside Streamlit against the same PAPER engine service.
  3. Run parity and failure-path tests.
  4. Retire Streamlit only after feature and safety parity.
- Do not rewrite the strategy during the UI migration. Strategy corrections and UI replacement require separate testable work packages.
- Final UI stack and migration design still require user approval.

## 11. Testing and completion standard

Before any future implementation is called complete, validate at least:

### Strategy/unit tests

- Latest completed close-to-previous-close velocity.
- No look-ahead or unfinished-candle entry.
- Candle deduplication.
- Real regime calculation with known directional and sideways fixtures.
- SIDEWAYS 1–5% and DIRECTIONAL 1–10% boundaries, including exact endpoints.
- Both-negative rejection.
- Moneyness/expiry guards per index.
- Quantity-aware projected net with fixed and variable charges.
- Negative/insufficient safety-buffer rejection.
- Index-specific lot/strike/expiry metadata.

### Multi-index/concurrency tests

- All five indices scanned independently.
- Observe-only index cannot execute.
- One global trade/reservation under simultaneous candidate arrival.
- Runtime selection snapshot behavior.
- Active trade remains monitored after deselection.
- No selection produces an explicit safe state.
- Candidate ranking is deterministic.

### Daily-state/P&L tests

- Prior-day loss does not trigger today's PAPER threshold.
- Today/week/month/year/all-time boundaries in IST.
- Deposits/withdrawals excluded from trading P&L.
- PAPER and LIVE separated.
- Restart reconstructs correct daily and cumulative state.

### Market-data failure tests

- Empty response.
- HTML/non-JSON response.
- HTTP error/rate limit.
- Timeout and retry exhaustion.
- Stale candle.
- Missing leg/quote.
- Out-of-order or duplicate candle.
- No entry on stale, partial, synthetic, or malformed data.

### PAPER/LIVE safety tests

- PAPER code path cannot instantiate/call broker order submission.
- Runtime mode snapshot cannot change from PAPER to LIVE mid-session.
- LIVE kill switch disabled by default.
- LIVE allocation firewall covers entries, retries, rotations, partial fills, and restart reconciliation.
- One position and capital reservation are atomic.
- Daily LIVE latch cannot be cleared by allocation/index-selection changes.

### UI tests

- Index All/one/many selection and runtime application.
- Diagnostics Start/Stop/top-count/download.
- Pass/fail reasons and calculations rendered correctly.
- Period P&L cards.
- Active-position monitoring after deselection.
- Connection loss and stale-state warning.
- No UI action can bypass backend validation.

### End-to-end PAPER scenarios

- Directional up/down.
- Sideways with IV expansion.
- Dual decay.
- Expiry and near-expiry.
- Gap/opening volatility.
- API interruption and recovery.
- Restart with open PAPER position.
- Multiple indices produce candidates simultaneously.
- Daily threshold crosses and new PAPER trades receive `-SL`.

Completion requires fresh test output plus code/UI review; passing unit tests alone is not enough.

## 12. Open design decisions and next actions

1. Finalize and approve the non-Streamlit UI architecture and migration phases.
2. Confirm whether runtime zero-selection means `Pause new entries` or is disallowed.
3. Present and approve detailed entry/exit, diagnostics, P&L, error-handling, and persistence designs.
4. Write a formal design specification only after approval.
5. Self-review the specification for contradictions, placeholders, and missing safety cases.
6. Obtain user review of the written specification.
7. Create a test-first implementation plan.
8. Do not implement trading/UI code until the user explicitly approves moving from design into implementation.

## 13. Handover update protocol

- Update `AI conversation/codex handover.md` before every assistant response.
- Record the date, new questions, decisions, discovered facts, file changes, verification evidence, and unresolved items.
- Do not treat a proposed design as implemented.
- Clearly distinguish `Observed`, `Confirmed`, `Approved`, `Proposed`, `Implemented`, and `Verified`.
- Never include access tokens, Dhan credentials, or other secrets.

## 14. Update log

### 2026-07-15 — Handover created

- Captured the July 14 safety, pricing, sizing, PAPER daily-stop, capital-ledger, LIVE-allocation, testing, Git, and documentation work.
- Captured the July 15 zero-entry investigation, confirmed regime/candle/daily-state/data-response defects, profitability examples, approved scan timing/bands, multi-index selection, rejection inspector, period P&L, and modular architecture.
- Added the new runtime checkbox index-selection requirement.
- Added the new request to assess and design a non-Streamlit UI.
- Reaffirmed that no new trading code is authorized yet.

### 2026-07-15 — Non-Streamlit UI recommendation prepared

- Recommended a phased separation into a UI-independent Python trading service, FastAPI control/read API, WebSocket event stream, and React/TypeScript client.
- Clarified that replacing Streamlit improves UI responsiveness, process isolation, real-time streaming, and testability, but does not automatically make the trading calculations faster; engine/data-path corrections remain separate work.
- Proposed serving the compiled frontend from the Python service for a one-command local application after development, avoiding permanent operational dependence on a separate frontend development server.
- Added server-authoritative runtime index selection: default All, one/many/all checkboxes, immutable selection snapshot per scan, audit log, and next-scan application.
- Proposed that zero selected indices be a safe `Pause new entries` state while all active-position risk/exit monitoring continues. User approval of this last semantic is pending.

### 2026-07-15 — Pause behavior approved and implementation authorized

- User approved zero selected indices as an explicit `Pause New Entries` state.
- While paused, new candidate execution is disabled, but any existing position must continue full one-second price, risk, hard-stop, trailing, hedge-cut, recovery, and EOD monitoring.
- User authorized proceeding with the new non-Streamlit UI and associated modular code changes.
- User restated the required quality bar: modular and simple boundaries, daily state strictly by trade date, explicit non-JSON market-data diagnostics and safe retry, corrected candidate/moneyness/dual-decay/projected-net logic, and rigorous code plus UI testing before completion claims.
- The canonical handover remains in the project and is mirrored to `C:\Users\LENOVO\Documents\Codex\2026-07-15\referenced-chatgpt-conversation-this-is-untrusted\outputs\AI conversation\codex handover.md` because that is where the user expected task outputs.

### 2026-07-15 — Implementation started (partial; not complete)

- Added approved design specification: `docs/superpowers/specs/2026-07-15-modular-multi-index-web-ui-design.md`.
- Added test-first implementation plan: `docs/superpowers/plans/2026-07-15-modular-multi-index-web-ui.md`.
- Established a reproducible baseline using `python -m pytest -q --basetemp .pytest-tmp`; baseline was 90 passed. The default Windows temp path had permission errors, so `.pytest-tmp` is now ignored.
- Added `application/performance_service.py` with IST Today/Week/Month/Year/All-time calculations, separate active P&L, and date-scoped daily risk.
- Added `Trade.execution_mode`, SQLite schema migration, and PAPER/LIVE/BACKTEST adapter population. Legacy rows safely default to `UNKNOWN` rather than silently mixing modes.
- Updated the current Streamlit breaker path to use today's date-scoped risk rather than cumulative historical realized P&L. Added a period selector as temporary parity support.
- Performance/date/mode targeted tests passed; full backend suite reached 96 passed at that checkpoint.
- Added `data/market_response.py` with typed empty/non-JSON/broker/exception failures, sanitized bounded preview, correlation ID, and bounded exponential retry.
- Integrated typed quote fetching into `LiveFeed`; exhausted quote failures set fail-closed feed state and publish an actionable error instead of leaking raw JSON decoder errors.
- Added `core/index_registry.py` for the five indices and `application/index_selection.py` for thread-safe immutable versioned All/one/many/zero selection plus audit events.
- Added FastAPI dependencies and initial `api/` presentation adapter. Verified API endpoints for health, index metadata, selection updates, stale-version conflict, unknown-index rejection, and static frontend serving.
- Added modular React/TypeScript/Vite client under `webui/`, with typed API client and separate `IndexSelector` component. It shows tradable/observe-only badges, All/individual checkboxes, and explicit Pause New Entries state.
- Added `run_web_app.bat`; FastAPI serves compiled React assets at localhost. Streamlit remains during parity.
- Frontend dependency audit reported zero vulnerabilities at installation time. Frontend component tests: 2 passed. Production frontend build succeeded.
- Fresh combined verification after the initial slice: backend `110 passed, 1 warning in 6.68s`; frontend `2 passed`; TypeScript/Vite production build succeeded. The warning is Starlette's TestClient/httpx deprecation notice and is not a test failure, but should be removed during dependency cleanup.
- This is an initial slice only. Completed-candle/regime correction, explainable pair pipeline, quantity-aware ranking, diagnostic capture, multi-index coordinator, engine controls, P&L API/cards, active position, console, journal, capital UI, WebSocket stream, and full PAPER parity remain open.

### 2026-07-15 — Web launcher virtual-environment dependency fix

- Observed: `run_web_app.bat` selected `.venv\Scripts\python.exe`, but FastAPI had previously been installed outside that virtual environment. Uvicorn therefore started from `.venv` and failed while importing `api.app` with `ModuleNotFoundError: No module named 'fastapi'`.
- Implemented: the launcher now selects the project `.venv` interpreter when present, checks that both `fastapi` and `uvicorn` import in that exact interpreter, installs the declared `requirements.txt` into it when the check fails, verifies the imports again, and only then starts the server with the same interpreter.
- Added `tests/test_web_distribution.py` coverage that protects the interpreter selection, dependency preflight/install, and Uvicorn invocation behavior.
- Verified with the project interpreter: FastAPI `0.139.0` and Uvicorn `0.51.0` import successfully.
- Verified targeted distribution/API suite: `5 passed, 1 warning in 1.55s`. The warning is the already-recorded Starlette TestClient/httpx deprecation notice.
- Safety: this launcher/dependency correction does not invoke the broker, place orders, change PAPER simulation behavior, or alter the user's `config.json` dates.
- Status: the reported startup dependency failure is fixed and verified. The broader non-Streamlit UI remains an incomplete initial slice and must not be described as production-ready.

### 2026-07-15 — Requested automatic Windows startup

- Confirmed by user: the FastAPI/React application now starts and serves successfully at `http://127.0.0.1:8000`.
- Requested: automatically run the local trading UI application whenever the PC is started.
- Safety boundary established: automatic startup may launch only the local web server/UI. It must never automatically start the trading engine, enable LIVE mode, or submit broker orders.
- Recommended deployment direction under review: a Windows Task Scheduler entry running under the user's account at sign-in, hidden, with restart-on-failure and a dedicated log. This is safer and easier to reverse than installing the development application as a Windows Service.
- Pending user decision: whether startup should occur at Windows user sign-in (recommended) or before sign-in as a machine-level service/task.

### 2026-07-15 — Automatic-start trigger approved; implementation design pending approval

- User approved automatic startup after Windows sign-in.
- Proposed task identity: a current-user Windows Scheduled Task named `AutoTrader Web UI`, triggered at this user's logon and run hidden.
- Proposed implementation is modular and reversible: a small hidden launcher, an installer, and an uninstaller under a focused startup/service scripts area; runtime output goes to an ignored application log.
- Proposed safeguards: one server instance only, fixed loopback binding `127.0.0.1:8000`, delayed startup for desktop readiness, restart-on-failure, explicit working directory, project `.venv` only, and no automatic browser opening.
- Critical safety invariant: the scheduled task starts only FastAPI/React. The trading engine remains stopped and no PAPER or LIVE entry process is started automatically. LIVE broker writes remain disabled in the current web build.
- Verification plan: test-first script/task contract tests, launcher/API regression tests, install/read-back of the scheduled task, and a health check without disrupting an already-running manual instance.

### 2026-07-15 — Server-backed operational web UI slice

- User confirmed the initial React UI loaded but reported that only index checkboxes worked; Period P&L, Position, and Pair Inspector were static placeholders.
- Scope decision: replace placeholders with real read models and explicit controls without fabricating scanner/engine behavior. Automatic Windows startup-task implementation was deferred when the user redirected work to the remaining UI.
- Added `application/dashboard_service.py`, a UI-independent read-model service over `TradeStore`, `CapitalLedger`, `PerformanceService`, and configuration. It validates PAPER/LIVE mode and exposes period performance, active-position data, journal rows, and capital snapshots.
- Added `application/diagnostic_capture.py`, a bounded thread-safe observational buffer with explicit Start/Stop, Top 5/10 validation, deterministic CSV/JSON export, and off-by-default behavior.
- Extended FastAPI with read-only endpoints: `GET /api/performance`, `GET /api/positions/active`, `GET /api/trades`, `GET /api/capital`, `GET /api/diagnostics`, diagnostic Start/Stop, and CSV/JSON download.
- Added dependency injection to `create_app` so API tests use isolated temporary trade and capital databases. No route was added for engine start or capital mutation, and no broker adapter is called.
- Added React components: `PerformanceCards`, `ActivePosition`, `PairDiagnostics`, `ActivityConsole`, `TradeJournal`, and `CapitalPanel`, plus typed client contracts and formatting helpers.
- Period P&L now supports Today/Week/Month/Year/All time. Realized, active, and total P&L are displayed separately and remain mode/date scoped.
- Active-position UI prominently shows Lots and Units/leg. Persisted positions without fresh marks explicitly display `Live mark unavailable`; the application does not invent current prices or P&L.
- Journal shows trade ID, time, pair, lots/units, exit reason, gross P&L, Dhan-style transaction costs, and net P&L.
- Capital panel shows PAPER equity, base capital, deposits/withdrawals, and recent ledger notes. It is intentionally read-only; stopped-engine mutation controls remain pending.
- Diagnostic Start/Stop and Top 5/10 selection work, and CSV/JSON downloads are available. The UI explicitly warns that scanner feed integration is still pending; no pair rows will appear until the multi-index coordinator feeds evaluations into the capture service.
- Activity Console currently shows bounded browser/server snapshot events and explicitly states that WebSocket runtime streaming is pending.
- TDD evidence: backend API/dashboard tests were first observed failing on missing service/signature; diagnostic capture tests were first observed failing on the missing module; frontend component tests were first observed failing on missing components and pending-integration disclosure.
- Fresh verification: backend `119 passed, 1 warning in 8.78s`; frontend `7 passed`; TypeScript/Vite production build succeeded. The remaining warning is Starlette TestClient/httpx deprecation.
- Isolated server smoke test on `127.0.0.1:8010`: health `ok`, safety `PAPER_ONLY_DURING_BUILD`, PAPER performance endpoint responded, diagnostic capture defaulted false, and compiled frontend returned HTTP 200. The temporary process was stopped afterward.
- User must stop the already-running older Uvicorn process and rerun `run_web_app.bat` so Python loads the newly added API routes; compiled assets alone are not sufficient for backend route updates.
- Preserved `config.json` dates `2026-06-09` and `2026-07-13`; its only visible diff remains the user's missing final newline.
- Still pending: completed-candle/real-feature path, explainable pair evaluator, quantity-aware profitability gate, multi-index coordinator, real diagnostic scan feed, engine lifecycle API/controls, one-second position marks, WebSocket events, capital mutations with stopped-engine enforcement, and full PAPER end-to-end parity. Do not call the overall UI/runtime complete.

### 2026-07-15 — Safety, price-integrity, and operational UI completion pass

**Implemented and verified**

- Added a completed-candle store and fed NIFTY option/spot ticks into it. Entry signals now use previous completed close versus latest completed close; unfinished or timestamp-misaligned CE/PE candles do not produce a candidate.
- Replaced placeholder regime inputs with aligned completed spot OHLC/VWAP/ATR feature calculation. The engine blocks new entries until sufficient real completed candles exist, while active-position risk/exit checks continue independently every second.
- Changed entry evaluation to once per completed candle with a 60-second scan interval. Both `config.json` and the `TradingConfig` default now agree on 60 seconds.
- Replaced unrestricted CE × PE execution layouts with an explicit nearest matched-ATM pair template. The wider chain is not exposed as an executable Cartesian matrix.
- Kept SIDEWAYS divergence at inclusive 1–5% and DIRECTIONAL divergence at inclusive 1–10%. Dual-decay candidates are rejected rather than treating the less-negative option as a winner.
- Added quantity-aware profitability using executable entry asks, conservative projected exit bids, dynamic equal lots, exact units, freeze-order slicing, Dhan-style turnover charges, scalable slippage, minimum net-profit buffer, and minimum return percentage.
- Added explainable scan diagnostics with pass/fail reasons and projected gross/cost/slippage/net/quantity details. Top 5/10 capture remains explicitly controlled and downloadable as CSV or JSON.
- Added a process-owned PAPER runtime service and web API lifecycle controls. The factory hard-locks `LiveEngine` to PAPER, and startup aborts if PAPER mode is not confirmed.
- Added an additional hard runtime invariant: the engine cannot be stopped while an open position requires one-second risk and exit monitoring.
- Added a WebSocket runtime snapshot stream for engine state, activity, active position, and diagnostics. Browser refresh/closure does not own or stop engine state.
- Added server-backed Start/Stop controls, Today/Week/Month/Year/All-time P&L, active lots/units and mark freshness, trade journal, live activity console, diagnostic controls/downloads, and stopped-engine PAPER target-equity adjustment.
- Corrected PAPER capital reconciliation. Current equity now includes mode-scoped TradeStore P&L plus orphaned append-only PAPER `TRADE_PNL` ledger rows from legacy trades, without double counting represented current trades. This fixes the observed incorrect ₹81,365.35 display after restoring an ₹8,634.65 balance to ₹45,000.
- PAPER target adjustments remain append-only deposits/withdrawals and require the engine stopped with no open position. The web slice exposes no LIVE fund-transfer mutation.
- Added an atomic global position reservation and deterministic multi-index coordinator boundary. Concurrency tests prove only one simultaneous candidate can reserve the slot; observe-only candidates cannot execute; failed execution releases the reservation; zero selection is Pause New Entries.
- Registered the current-user Windows Scheduled Task `AutoTrader Web UI` with a 30-second logon delay, hidden PowerShell launcher, single-instance behavior, and bounded restart-on-failure. It starts only FastAPI/React at `127.0.0.1:8000`; it does not start the trading engine, enable LIVE, or submit orders.
- Corrected misleading UI readiness. NIFTY is shown as `Connected · tradable`. BANKNIFTY and FINNIFTY retain approved permission but show `Approved · feed pending`; MIDCPNIFTY and NIFTYNXT50 show observe-only/feed-pending. Pending feeds are non-executable and are no longer presented as connected.
- Removed a duplicate `PairRanker.__init__` definition and aligned the default scan interval with runtime configuration.

**Fresh verification evidence**

- Backend: `147 passed, 1 warning in 10.96s` using `python -m pytest -q --basetemp .pytest-tmp`.
- Runtime/API stop-safety subset: `7 passed, 1 warning`.
- Atomic reservation/coordinator subset: `5 passed`.
- Frontend: `8 passed` using Vitest.
- Production frontend: TypeScript and Vite build succeeded; compiled assets were regenerated under `webui/dist`.
- Isolated compiled-app smoke test on `127.0.0.1:8011`: health `ok`, safety `PAPER_ONLY_DURING_BUILD`, root HTTP 200, NIFTY connected `true`, BANKNIFTY connected `false`; the temporary process was stopped afterward.
- `git diff --check` produced no whitespace errors; only Windows LF-to-CRLF notices were emitted.
- The single warning is the known Starlette TestClient/httpx deprecation warning; it does not affect runtime behavior.
- `config.json` dates remain exactly `backtest_from_date: 2026-06-09` and `backtest_to_date: 2026-07-13`.

**Explicit remaining boundary — not claimed complete**

- Production market-data and strategy execution are currently connected only for NIFTY. BANKNIFTY, FINNIFTY, MIDCPNIFTY, and NIFTYNXT50 require per-index quote caches, spot/option candle feeds, validated instrument metadata, index-specific lot/freeze/strike settings, and production wiring into the atomic coordinator before they may be called connected.
- The coordinator domain/concurrency boundary exists and is tested, but the legacy production `LiveEngine` still uses the NIFTY adapter. No additional index is allowed to execute merely because its checkbox is selected.
- LIVE remains outside this PAPER validation UI. No real broker-order test was performed. LIVE activation still requires a separate readiness audit, broker-confirmed allocation enforcement, reconciliation, and explicit user authorization.
- The running Uvicorn process must be restarted (or the PC signed out/in for the scheduled task) and the browser hard-refreshed to load the regenerated backend/frontend files.

### 2026-07-15 — Git publication guidance requested

- User requested step-by-step instructions to publish the verified changes to GitHub; no staging, commit, push, or PR action was authorized or performed by Codex in this response.
- Current branch confirmed as `codex/capital-live-safety-readiness-docs`, with remote `origin` pointing to `pdrevanthstock-max/chatgpt_auto_trader`.
- Publication guidance uses selective staging and explicitly excludes `docs/superpowers/` so planning/workflow artifacts are not committed. It also avoids `git add .` and preserves the verified `config.json` dates.
- Recommended pre-commit evidence remains: backend 147 passed, frontend 8 passed, production build succeeded, and `git diff --check` passed.

### 2026-07-15 — Staging output reviewed

- Confirmed `docs/superpowers/` is untracked (`??`), not staged, so `git restore --staged docs/superpowers` is unnecessary.
- Detected and removed pre-existing trailing spaces in the handover header that caused `git diff --cached --check` to fail.
- Detected staged generated artifact `webui/tsconfig.tsbuildinfo`; guidance requires unstaging it before commit.

### 2026-07-15 — Windows pytest temp-directory failure diagnosed

- User's pre-commit run reported `123 passed, 24 errors`; every error occurred during pytest temporary-directory setup/cleanup with Windows `PermissionError [WinError 5]` against the reused `.pytest-tmp` folder. These were infrastructure errors, not failed strategy/runtime assertions.
- Re-ran the complete backend suite with a new isolated temp directory and disabled pytest cache: `python -m pytest -q -p no:cacheprovider --basetemp .pytest-run-git-20260715`.
- Fresh result: `147 passed, 1 warning in 8.25s`. The warning remains the known Starlette TestClient/httpx deprecation notice.
- Added `.pytest-run-*/` to `.gitignore`; no locked temp directory was deleted and no trading code or configuration dates were changed.
