# AutoTrader Runtime Architecture

**Status:** PAPER validation runtime  
**Scope:** Multi-index data acquisition, dynamic ATM/ITM selection, strategy cadence, diagnostics, execution serialization, recovery, and UI updates.

## 1. Cadence and concurrency summary

| Path | Frequency | Call shape | Parallel or sequential? | Safety behavior |
|---|---:|---|---|---|
| Dhan quote polling | Every 5 seconds | One combined request containing five `IDX_I` spot IDs and up to approximately 50 `NSE_FNO` option IDs | One network call; response rows are demultiplexed sequentially into isolated caches | Up to three bounded attempts on a failed/invalid response; no synthetic fallback |
| Dynamic strike resolution | Every quote cycle after spots exist | Five CE strikes and five PE strikes per index | Sequential, deterministic loop over index metadata | Uses current spot and index-specific strike step; no fixed numeric strikes |
| Spot/option candle aggregation | Every successful quote response | Ticks are assigned to symbol-specific one-minute candle keys | Sequential response processing; isolated state | Invalid/non-positive prices are skipped |
| Engine risk loop | Every 1 second | Reads current configuration and active position state | One background engine thread | If a position is open, risk/exits run first; replacement discovery runs separately on the 60-second completed-candle cadence |
| Entry scan | Every 60 seconds while flat and inside entry window | One `MultiIndexRuntime.scan()` call | Selected indices are scanned sequentially in sorted symbol order | Requires ten completed one-minute spot candles independently per index |
| Active-position monitoring | Every 1 second | Reads the active trade's index cache for risk, then scans all selected indices only when the 60-second rotation cadence is due | Risk is sequential and first; index scanners are then called sequentially in sorted-symbol order | Missing/stale active quotes fail closed; a replacement can only be a serialized ROTATION, never a second ENTRY |
| Execution queue | Event driven | One `ExecutionSignal` at a time | Serialized FIFO worker | Global position reservation prevents simultaneous entries |
| Browser WebSocket snapshot | Every 1 second per connected browser | Runtime, position, diagnostics | One coroutine per browser connection | Browser is display/control only; it never owns risk state |
| REST performance/trades/capital refresh | Every 5 seconds from React | Three read-only requests | Browser launches them together | Does not affect engine or execution state |

## 2. End-to-end component flow

```mermaid
flowchart TB
    USER[User Browser]
    TASK[Windows Scheduled Task<br/>starts after sign-in]
    API[FastAPI and Uvicorn<br/>127.0.0.1:8000]
    REACT[React Control Center]
    ENGINE[LiveEngine<br/>PAPER session lock]
    FEED[LiveFeed thread<br/>5-second cadence]
    DHAN[Dhan Market Quote API]
    MASTER[Local instrument master<br/>loaded at feed startup]

    TASK --> API
    API --> REACT
    USER <--> REACT
    API --> ENGINE
    ENGINE --> FEED
    MASTER --> FEED

    FEED -->|one combined quote request| DHAN
    DHAN -->|IDX_I and NSE_FNO response| FEED

    subgraph REGISTRY[Authoritative index registry]
      N[NIFTY<br/>ID 13 · step 50 · lot 65<br/>tradable]
      B[BANKNIFTY<br/>ID 25 · step 100 · lot 30<br/>tradable]
      F[FINNIFTY<br/>ID 27 · step 100 · lot 60<br/>tradable]
      M[MIDCPNIFTY<br/>ID 442 · step 25 · lot 120<br/>observe only]
      X[NIFTYNXT50<br/>ID 38 · step 100 · lot 25<br/>observe only]
    end

    REGISTRY --> FEED

    subgraph CACHES[Strictly isolated market contexts]
      NC[NIFTY cache and candles]
      BC[BANKNIFTY cache and candles]
      FC[FINNIFTY cache and candles]
      MC[MIDCPNIFTY cache and candles]
      XC[NIFTYNXT50 cache and candles]
    end

    FEED -->|demultiplex by security ID| NC
    FEED -->|demultiplex by security ID| BC
    FEED -->|demultiplex by security ID| FC
    FEED -->|demultiplex by security ID| MC
    FEED -->|demultiplex by security ID| XC

    subgraph SCANNERS[60-second entry evaluation while flat]
      NS[NIFTY scanner]
      BS[BANKNIFTY scanner]
      FS[FINNIFTY scanner]
      MS[MIDCPNIFTY diagnostics]
      XS[NIFTYNXT50 diagnostics]
    end

    NC --> NS
    BC --> BS
    FC --> FS
    MC --> MS
    XC --> XS

    NS --> COORD[MultiIndexCoordinator]
    BS --> COORD
    FS --> COORD
    MS -->|never executable| DIAG[Diagnostic capture]
    XS -->|never executable| DIAG
    NS --> DIAG
    BS --> DIAG
    FS --> DIAG

    COORD -->|best tradable projected net| SLOT[Global position reservation]
    SLOT --> QUEUE[Serialized execution queue]
    QUEUE --> PAPER[PAPER executor for selected index]
    PAPER --> DB[(SQLite trade store)]
    PAPER --> RECOVERY[Crash-recovery state]

    ENGINE -->|1-second active risk path| ACTIVE[Exit and hedge-cut checks]
    ACTIVE -->|if no immediate exit and 60 seconds elapsed| ROTSCAN[All selected-index replacement scan]
    ROTSCAN -->|best eligible tradable index only| QUEUE
    ACTIVE --> QUEUE

    DB --> DASH[Dashboard service]
    RECOVERY --> ENGINE
    DIAG --> API
    DASH --> API
    API -->|WebSocket every 1 second| REACT
```

## 3. Candidate universe and rejection order

For each selected index the current spot is rounded with that index's own strike step on every quote cycle. Numeric strikes are therefore dynamic option-chain selections, not fixed constants.

- Established universe: CE ATM plus CE ITM1-ITM4 crossed with PE ATM plus PE ITM1-ITM4 (25 combinations).
- SIDEWAYS expiry universe: ATM is removed, leaving 16 ITM x ITM combinations.
- PAPER directional research: four additional CE OTM1/OTM2 x PE OTM1/OTM2 combinations. These are disabled in LIVE and stop at 12:00 IST on expiry day.
- SIDEWAYS divergence: 1-5% is normal. The 0.75-1% and 5-6% edge buffers require at least INR 200 projected net and 0.50% projected return. Values outside 0.75-6% are rejected.
- DIRECTIONAL divergence remains 1-10%; therefore an 8% pair is directional-only.
- Every candidate still passes direction alignment, dual-decay, premium ratio, quote integrity/synchronization, projected net/return, capital affordability, sizing and final execution validation.

Index scanners are deliberately sequential inside one engine thread. This avoids races in shared reservation and diagnostic state. The market-data request is batched across all five indices, then demultiplexed into isolated caches. The coordinator compares NIFTY, BANKNIFTY and FINNIFTY candidates globally; MIDCPNIFTY and NIFTYNXT50 remain diagnostic-only.

## 4. Active-position replacement flow

```mermaid
flowchart LR
    TICK[1-second engine tick] --> RISK[Active-index quote and hard exit checks]
    RISK -->|exit required| EXIT[Serialized EXIT signal]
    RISK -->|no exit| DUE{60-second scan due?}
    DUE -->|no| HOLD[Keep position]
    DUE -->|yes| ALL[Scan all selected indices]
    ALL --> ELIG[Keep tradable candidates passing all gates]
    ELIG --> BEST[Best projected-net candidate]
    BEST --> ECON{Active net at least INR 100 and improvement at least INR 100?}
    ECON -->|no| HOLD
    ECON -->|yes| ROT[One serialized ROTATION signal]
    ROT --> CLOSE[Confirm old pair close]
    CLOSE --> OPEN[Open replacement using its index cache and lot size]
```

The global reservation stays active during close-to-replacement serialization. A successful normal exit releases it, allowing the next independent entry scan to reserve the slot.

## 5. Market quote cycle

```mermaid
sequenceDiagram
    participant LF as LiveFeed
    participant REG as IndexRegistry
    participant DH as Dhan Quote API
    participant NC as NIFTY Cache
    participant BC as BANK Cache
    participant FC as FIN Cache
    participant MC as MIDCP Cache
    participant XC as NXT50 Cache

    loop Every 5 seconds
        LF->>REG: Read all five index specifications
        LF->>LF: Read current spot from each isolated cache
        LF->>LF: Recalculate ATM and ATM/ITM1-ITM4 numeric strikes
        Note over LF: First cycle after startup can contain only five spots.<br/>Next cycle adds up to ten options per index.
        LF->>DH: ONE combined request: 5 IDX_I + up to ~50 NSE_FNO IDs
        alt Valid success response
            DH-->>LF: Combined quote response
            LF->>NC: Apply NIFTY rows
            LF->>BC: Apply BANKNIFTY rows
            LF->>FC: Apply FINNIFTY rows
            LF->>MC: Apply MIDCPNIFTY rows
            LF->>XC: Apply NIFTYNXT50 rows
        else Empty, non-JSON, invalid, or failed response
            LF->>DH: Retry through bounded policy, maximum 3 attempts
            Note over LF,DH: If all attempts fail, caches are not fabricated.<br/>Execution waits for valid fresh data.
        end
    end
```

### Network-call interpretation

- The application does **not** make five simultaneous Dhan quote calls.
- In normal operation it makes **one combined request every five seconds**, approximately **12 requests per minute**.
- The five indices are separated after the response using security-ID mappings.
- A failure can temporarily produce up to three request attempts for that polling cycle.
- Direct index spot prices use the `IDX_I` segment. Option prices use `NSE_FNO`.

## 6. Dynamic cross-strike selection

For each index on every quote cycle:

```text
ATM = round(current_spot / strike_step) × strike_step

CE universe = ATM, ATM - 1 step, ATM - 2 steps, ATM - 3 steps, ATM - 4 steps
PE universe = ATM, ATM + 1 step, ATM + 2 steps, ATM + 3 steps, ATM + 4 steps
```

Example for NIFTY spot `24,128`, step `50`:

```text
ATM: 24,150
CE: 24,150 / 24,100 / 24,050 / 24,000 / 23,950
PE: 24,150 / 24,200 / 24,250 / 24,300 / 24,350
```

These numbers are not constants. If spot moves far enough to change ATM, the next quote request uses the new numeric strikes.

The executable pair universe is:

- Normal day or confirmed directional expiry: `5 CE × 5 PE = 25` pairs.
- SIDEWAYS exact-expiry session: remove ATM from both legs, producing `4 CE × 4 PE = 16` ITM×ITM pairs.
- PAPER confirmed-direction research before the expiry-day 12:00 cutoff adds four bounded OTM pairs: CE OTM1/OTM2 crossed with PE OTM1/OTM2. LIVE never receives these templates.

## 7. Entry-scan cycle

```mermaid
sequenceDiagram
    participant E as LiveEngine 1-second loop
    participant R as MultiIndexRuntime
    participant S as Per-index scanners
    participant D as Diagnostics
    participant C as Coordinator
    participant Q as Execution queue

    loop Every 1 second
        E->>E: Refresh config and today's date-scoped risk
        alt Active position exists
            E->>E: Monitor quotes, hard stop, exits, and hedge cut
            opt No immediate exit and 60-second rotation scan is due
                E->>R: scan_for_rotation(selected indices)
                R->>D: Record all per-index diagnostics
                R-->>E: Best eligible tradable replacement
                E->>Q: Enqueue at most one serialized ROTATION
            end
        else Flat and at least 60 seconds since prior entry scan
            E->>R: scan(selected indices)
            loop Each selected symbol in sorted order
                R->>R: Require 10 completed spot candles
                R->>S: Run isolated regime, pairs, filters, rank, size, validation
                S-->>R: Candidate or rejection diagnostics
            end
            R->>D: Record diagnostics for all selected indices
            R->>C: Compare tradable candidates
            C->>C: Choose projected net, then confidence, then symbol
            C->>C: Atomically reserve the one global position slot
            C->>Q: Enqueue at most one PAPER entry
        end
    end
```

### Scan-parallelism interpretation

- Per-index scanners own separate caches and strategy objects.
- They are **logically isolated**, but the current implementation invokes them **sequentially**, in sorted symbol order.
- They are not five parallel Python threads.
- Sequential execution is intentional for five small candidate universes because it provides deterministic ordering and avoids shared reservation/diagnostic races.
- The one-minute entry signal still evaluates every selected ready index during the same scan cycle.

## 8. Candidate pipeline inside each index

```mermaid
flowchart LR
    READY[10 completed spot candles] --> REGIME[Independent regime and trend]
    REGIME --> PAIRS[25 normal/directional pairs<br/>or 16 sideways-expiry pairs]
    PAIRS --> BOOK[Quote integrity and emergency spread]
    BOOK --> DIV[Completed-candle CE/PE divergence]
    DIV --> SIGNAL[Regime-specific signal gates]
    SIGNAL --> ECON[Dual-decay, ratio 2.5,<br/>projected cost/slippage/net]
    ECON --> RANK[Rank using current available equity]
    RANK --> SIZE[Lots and units using index lot size]
    SIZE --> FINAL[Final execution validation]
    FINAL --> RESULT[Candidate or explicit rejection reason]
```

## 9. Execution and risk serialization

- The coordinator permits only one global active position across all indices.
- Observe-only indices contribute diagnostics but can never win execution.
- A reservation is acquired before queueing an entry.
- The execution queue processes signals one at a time.
- PAPER executor selection is based on `TradePlan.index_symbol`.
- Failed PAPER fills release the reservation so the flat engine cannot deadlock.
- Crash-recovered open positions reacquire the reservation.
- Active-position risk is checked every second using only that trade's index cache.
- The current web runtime refuses multi-index LIVE entry and does not expose a LIVE order endpoint.

## 10. UI and diagnostic flow

```mermaid
flowchart LR
    ENGINE[Engine state] --> WS[WebSocket snapshot<br/>every 1 second]
    POSITION[Active position view] --> WS
    DIAG[Diagnostic snapshot] --> WS
    WS --> UI[React UI]
    UI --> TILES[Live per-index strike tiles]
    UI --> TABS[Index-specific diagnostic tabs]
    UI --> TABLE[Bounded 20-column table]
    UI --> LOGS[Activity console]
```

Implemented Pair Inspector behavior:

- Top 5/10 is calculated and retained **independently per selected index per scan cycle**; BANKNIFTY no longer consumes a global prefix.
- Show one tab per index with captured-count and readiness indicators.
- Show 14 fixed primary columns with horizontal overflow handling.
- Keep overflow fields in a row detail drawer.
- Preserve every field in CSV/JSON downloads.
- Show per-index matrix, funnel, capital affordability, and global winner/runner-up comparison from server diagnostic fields. React does not make trading decisions.

## 11. Failure behavior

| Failure | Result |
|---|---|
| Dhan empty/non-JSON response | Bounded retry; no fabricated quotes |
| One index lacks spot | That index reports `SPOT_NOT_READY`; other indices continue |
| Fewer than ten completed spot candles | That index reports `COMPLETED_CANDLES_NOT_READY` |
| Missing option contract mapping | Missing strike is omitted; invalid pair cannot execute |
| Stale/asynchronous option candles | Pair rejected |
| Both option legs decay | Pair rejected |
| Projected net is negative after costs/slippage | Pair rejected |
| No safe capital-sized quantity | Pair rejected |
| Existing or recovered position | Global slot blocks every new entry |
| PAPER limit never becomes executable | Timeout; no Trade created |
| Browser closes or UI crashes | Backend risk loop continues independently |
| Web service restarts | Crash-recovery state is loaded before entry scanning |

## 12. Improvement checkpoints

1. Implement fair per-index diagnostic capture before evaluating scanner quality from Pair Inspector counts.
2. Add the server-authoritative live strike-universe endpoint/snapshot.
3. Add CI workflows before making status checks mandatory in GitHub branch protection.
4. Keep quote polling batched unless measured latency proves a bottleneck; parallel Dhan calls would increase rate-limit and partial-update risk.
5. Measure total per-index scan duration. Parallelize only if the deterministic sequential scan cannot remain comfortably below the 60-second cadence.
