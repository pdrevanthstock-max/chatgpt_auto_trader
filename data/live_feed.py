import logging
import threading
import time
import pandas as pd
from datetime import datetime
from pathlib import Path
from data.market_cache import market_cache
from config.settings import DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
from dhanhq import DhanContext, dhanhq
from data.market_response import RetryPolicy
from data.candle_store import completed_candles, option_candle_key, spot_candle_key

logger = logging.getLogger("AutoTrader")

class LiveFeed:
    """
    Fetches real-time option quotes from Dhan API using the security_id_list CSV mapping
    and updates MarketCache with actual market prices and calculated synthetic spot.
    Fails closed without generating synthetic prices when initialization fails.
    """
    def __init__(self, engine=None) -> None:
        self._running = False
        self._thread = None
        self.strike_map = {}
        self.id_map = {}
        self.active_expiry = None
        self.fallback_engaged = False
        self.client = None
        self.engine = engine
        self.quote_retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.5)

    def log_to_engine(self, message: str) -> None:
        if self.engine is not None:
            self.engine.log_activity(f"LiveFeed: {message}")
        logger.info(f"LiveFeed: {message}")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Live Feed connection stopped")

    def _fetch_quotes(self, security_ids: list[int], correlation_id: str) -> dict | None:
        """Fetch a quote batch with typed, bounded, fail-closed retries."""
        result = self.quote_retry_policy.run(
            lambda: self.client.quote_data({"NSE_FNO": security_ids}),
            endpoint="quote_data",
            correlation_id=correlation_id,
        )
        if not result.ok:
            self.fallback_engaged = True
            code = result.error_code.value if result.error_code else "UNKNOWN"
            self.log_to_engine(
                f"Quote batch blocked after {result.attempt_count} attempt(s): "
                f"{code}. {result.message} Correlation: {correlation_id}."
            )
            return None
        self.fallback_engaged = False
        return result.value

    def _initialize_mapping(self) -> bool:
        """Loads F&O option security mappings from CSV."""
        try:
            csv_path = Path("security_id_list.csv")
            if not csv_path.exists():
                raise FileNotFoundError("security_id_list.csv not found in workspace root.")

            self.log_to_engine("Loading security_id_list.csv mapping...")
            nifty_rows = []
            for chunk in pd.read_csv(csv_path, chunksize=100000, low_memory=False):
                chunk.columns = chunk.columns.str.strip()
                chunk["SEM_EXM_EXCH_ID"] = chunk["SEM_EXM_EXCH_ID"].astype(str).str.strip()
                chunk["SEM_SEGMENT"] = chunk["SEM_SEGMENT"].astype(str).str.strip()
                chunk["SEM_TRADING_SYMBOL"] = chunk["SEM_TRADING_SYMBOL"].astype(str).str.strip()
                
                matched = chunk[
                    (chunk["SEM_EXM_EXCH_ID"] == "NSE") &
                    (chunk["SEM_SEGMENT"] == "D") &
                    (chunk["SEM_TRADING_SYMBOL"].str.startswith("NIFTY-", na=False))
                ]
                if not matched.empty:
                    nifty_rows.append(matched)

            if not nifty_rows:
                raise ValueError("No Nifty F&O rows found in CSV.")

            df_all = pd.concat(nifty_rows)
            df_all["expiry_parsed"] = pd.to_datetime(df_all["SEM_EXPIRY_DATE"]).dt.date

            # Determine active expiry date dynamically (earliest expiry >= today)
            today_date = datetime.now().date()
            future_expiries = sorted([d for d in df_all["expiry_parsed"].unique() if d >= today_date])
            if not future_expiries:
                raise ValueError(f"No active expiries found in CSV >= {today_date}")

            self.active_expiry = future_expiries[0]
            market_cache.set_active_expiry(self.active_expiry)
            self.log_to_engine(f"Active Expiry selected: {self.active_expiry}")

            expiry_df = df_all[df_all["expiry_parsed"] == self.active_expiry]
            
            self.strike_map.clear()
            self.id_map.clear()
            
            for _, row in expiry_df.iterrows():
                strike = float(row["SEM_STRIKE_PRICE"])
                opt_type = str(row["SEM_OPTION_TYPE"]).strip()
                sec_id = int(row["SEM_SMST_SECURITY_ID"])
                self.strike_map[(strike, opt_type)] = sec_id
                self.id_map[sec_id] = (strike, opt_type)
                market_cache.set_security_id(int(strike), opt_type, sec_id)

            self.log_to_engine(f"Mapped {len(self.strike_map)} option contracts for {self.active_expiry}.")
            
            # Initialize Dhan Context
            if not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
                raise ValueError("Dhan Client ID or Access Token is missing in .env config.")
            
            ctx = DhanContext(client_id=DHAN_CLIENT_ID, access_token=DHAN_ACCESS_TOKEN)
            self.client = dhanhq(ctx)
            return True

        except Exception as e:
            logger.error(
                f"LiveFeed failed initialization: {e}. "
                "Synthetic pricing is disabled; PAPER/LIVE execution remains blocked."
            )
            self.log_to_engine(
                f"Initialization failed: {e}. Synthetic pricing is disabled and "
                "execution is blocked until the live feed recovers."
            )
            self.fallback_engaged = True
            return False

    def _run(self) -> None:
        initialized = self._initialize_mapping()

        if not initialized:
            logger.error(
                "LiveFeed stopped after initialization failure; MarketCache will "
                "remain empty rather than use synthetic prices."
            )
            self._running = False
            return
        
        # Spot price tracking
        spot = 24300.0
        
        while self._running:
            try:
                now = datetime.now()
                
                # REAL-TIME POLLING FROM DHAN
                # Identify ATM strike based on last known spot
                atm = int(round(spot / 50.0) * 50)
                
                # Get active trade strikes from engine dynamically to guarantee live P&L updates
                active_strikes = []
                trade = self.engine.active_trade if self.engine is not None else None
                if trade is not None and trade.is_open:
                    active_strikes.extend([float(trade.strike_ce), float(trade.strike_pe)])

                # Fetch closest 15 strikes (steps of 50, e.g. ATM - 350 to ATM + 350)
                test_strikes = [float(s) for s in range(atm - 350, atm + 400, 50)]
                for s in active_strikes:
                    if s not in test_strikes:
                        test_strikes.append(s)
                sec_ids = []
                for s in test_strikes:
                    if (s, "CE") in self.strike_map:
                        sec_ids.append(self.strike_map[(s, "CE")])
                    if (s, "PE") in self.strike_map:
                        sec_ids.append(self.strike_map[(s, "PE")])

                if not sec_ids:
                    time.sleep(5)
                    continue

                request_started = time.perf_counter()
                correlation_id = f"quote-{now.strftime('%Y%m%d-%H%M%S')}"
                res = self._fetch_quotes(sec_ids, correlation_id=correlation_id)
                latency_ms = int((time.perf_counter() - request_started) * 1000)
                if res is None:
                    time.sleep(5)
                    continue
                
                if res.get("status") == "success":
                    outer_data = res.get("data", {}).get("data", {})
                    data = outer_data.get("NSE_FNO", {})
                    
                    ce_prices = {}
                    pe_prices = {}
                    
                    # Update all polled contracts in MarketCache
                    for k, v in data.items():
                        sec_id = int(k)
                        if sec_id not in self.id_map:
                            continue
                        strike, opt_type = self.id_map[sec_id]
                        
                        ltp = v.get("last_price", 0.0)
                        bid_list = v.get("depth", {}).get("buy", [])
                        ask_list = v.get("depth", {}).get("sell", [])
                        
                        bid = bid_list[0].get("price", ltp) if bid_list else ltp
                        ask = ask_list[0].get("price", ltp) if ask_list else ltp
                        
                        ohlc = v.get("ohlc", {})
                        open_val = ohlc.get("open", ltp)
                        
                        # Populate options details in MarketCache
                        market_cache.update_option(int(strike), opt_type, {
                            "bid": bid,
                            "ask": ask,
                            "last": ltp,
                            "open": open_val,
                            "volume": v.get("volume", 0) or 0,
                            "oi": v.get("oi", 0) or 0,
                            "timestamp": now
                        })
                        completed_candles.add_tick(
                            option_candle_key("NIFTY", strike, opt_type),
                            now,
                            float(ltp),
                            volume=int(v.get("volume", 0) or 0),
                            oi=int(v.get("oi", 0) or 0),
                        )
                        
                        if opt_type == "CE":
                            ce_prices[strike] = ltp
                        else:
                            pe_prices[strike] = ltp

                    # Find the ATM strike based on call-put parity closest match
                    curr_atm = None
                    min_diff = float("inf")
                    for s in test_strikes:
                        if s in ce_prices and s in pe_prices:
                            diff = abs(ce_prices[s] - pe_prices[s])
                            if diff < min_diff:
                                min_diff = diff
                                curr_atm = s

                    if curr_atm is not None:
                        # Synthetic Nifty spot calculation
                        spot = curr_atm + ce_prices[curr_atm] - pe_prices[curr_atm]
                        market_cache.update_spot(spot, now)
                        completed_candles.add_tick(
                            spot_candle_key("NIFTY"), now, float(spot)
                        )
                        
                    market_cache.update_health(latency_ms=latency_ms)
                else:
                    logger.warning(f"Dhan live quote query returned failure: {res}")
                
                time.sleep(5) # Poll quotes every 5 seconds to comply with rate limits

            except Exception as loop_err:
                logger.error(f"Error in LiveFeed polling cycle: {loop_err}")
                time.sleep(5)
