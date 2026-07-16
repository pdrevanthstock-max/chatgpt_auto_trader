from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Mapping

import pandas as pd
from dhanhq import DhanContext, dhanhq

from config.settings import DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID
from core.index_registry import IndexRegistry
from data.candle_store import completed_candles, option_candle_key, spot_candle_key
from data.market_cache import MarketCacheRegistry, market_caches
from data.market_response import RetryPolicy


logger = logging.getLogger("AutoTrader")


class LiveFeed:
    """Polls one bounded quote batch into isolated per-index market contexts."""

    def __init__(
        self,
        engine=None,
        *,
        index_registry: IndexRegistry | None = None,
        cache_registry: MarketCacheRegistry | None = None,
        instrument_path: Path | str = "security_id_list.csv",
    ) -> None:
        self._running = False
        self._thread = None
        self.registry = index_registry or IndexRegistry.default()
        self.caches = cache_registry or market_caches
        self.instrument_path = Path(instrument_path)
        self.strike_maps: dict[str, dict[tuple[float, str], int]] = {}
        self.strike_map: dict[tuple[float, str], int] = {}
        self.id_map: dict[int, tuple[str, float, str]] = {}
        self.active_expiries: dict[str, object] = {}
        self.active_expiry = None
        self.fallback_engaged = False
        self.client = None
        self.engine = engine
        self.quote_retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.5)

    def log_to_engine(self, message: str) -> None:
        if self.engine is not None:
            self.engine.log_activity(f"LiveFeed: {message}")
        logger.info("LiveFeed: %s", message)

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

    def _fetch_quotes(
        self,
        request: Mapping[str, list[int]] | list[int],
        correlation_id: str,
    ) -> dict | None:
        """Fetch a quote batch with typed, bounded, fail-closed retries."""
        payload = {"NSE_FNO": request} if isinstance(request, list) else dict(request)
        result = self.quote_retry_policy.run(
            lambda: self.client.quote_data(payload),
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

    @staticmethod
    def _segments(response: Mapping[str, object]) -> Mapping[str, object]:
        data = response.get("data", {})
        if isinstance(data, Mapping) and isinstance(data.get("data"), Mapping):
            data = data["data"]
        return data if isinstance(data, Mapping) else {}

    def _initialize_mapping(self) -> bool:
        """Validate and load the nearest active expiry for every supported index."""
        try:
            if not self.instrument_path.exists():
                raise FileNotFoundError(f"{self.instrument_path} not found.")

            self.log_to_engine(f"Loading {self.instrument_path.name} multi-index mapping...")
            matched_rows = []
            prefixes = tuple(f"{symbol}-" for symbol in self.registry.symbols)
            for chunk in pd.read_csv(self.instrument_path, chunksize=100_000, low_memory=False):
                chunk.columns = chunk.columns.str.strip()
                exchange = chunk["SEM_EXM_EXCH_ID"].astype(str).str.strip()
                segment = chunk["SEM_SEGMENT"].astype(str).str.strip()
                trading_symbol = chunk["SEM_TRADING_SYMBOL"].astype(str).str.strip()
                matched = chunk[
                    exchange.eq("NSE")
                    & segment.eq("D")
                    & trading_symbol.str.startswith(prefixes, na=False)
                ].copy()
                if not matched.empty:
                    matched["_symbol"] = trading_symbol[matched.index].str.split("-").str[0]
                    matched_rows.append(matched)

            if not matched_rows:
                raise ValueError("No supported index option rows found in instrument master.")
            all_rows = pd.concat(matched_rows, ignore_index=True)
            all_rows["_expiry"] = pd.to_datetime(
                all_rows["SEM_EXPIRY_DATE"], errors="coerce"
            ).dt.date
            today = datetime.now().date()

            self.strike_maps.clear()
            self.id_map.clear()
            self.active_expiries.clear()
            for symbol in sorted(self.registry.symbols):
                spec = self.registry.get(symbol)
                rows = all_rows[
                    (all_rows["_symbol"] == symbol)
                    & (all_rows["_expiry"] >= today)
                ]
                if rows.empty:
                    raise ValueError(f"No active {symbol} option expiry found on or after {today}.")
                expiry = sorted(rows["_expiry"].dropna().unique())[0]
                expiry_rows = rows[rows["_expiry"] == expiry]
                lots = {
                    int(float(value))
                    for value in expiry_rows["SEM_LOT_UNITS"].dropna()
                }
                if lots != {spec.lot_size}:
                    raise ValueError(
                        f"{symbol} lot-size mismatch: registry {spec.lot_size}, master {sorted(lots)}."
                    )
                strikes = sorted({
                    int(float(value))
                    for value in expiry_rows["SEM_STRIKE_PRICE"].dropna()
                    if float(value) > 0.0
                })
                positive_diffs = [
                    right - left
                    for left, right in zip(strikes, strikes[1:])
                    if right > left
                ]
                if not positive_diffs or min(positive_diffs) != spec.strike_step:
                    raise ValueError(
                        f"{symbol} strike-step mismatch: registry {spec.strike_step}, "
                        f"master minimum {min(positive_diffs) if positive_diffs else 'missing'}."
                    )

                cache = self.caches.get(symbol)
                cache.set_active_expiry(expiry)
                mapping: dict[tuple[float, str], int] = {}
                for _, row in expiry_rows.iterrows():
                    strike = float(row["SEM_STRIKE_PRICE"])
                    option_type = str(row["SEM_OPTION_TYPE"]).strip().upper()
                    if strike <= 0.0 or option_type not in {"CE", "PE"}:
                        continue
                    security_id = int(row["SEM_SMST_SECURITY_ID"])
                    mapping[(strike, option_type)] = security_id
                    self.id_map[security_id] = (symbol, strike, option_type)
                    cache.set_security_id(int(strike), option_type, security_id)
                self.strike_maps[symbol] = mapping
                self.active_expiries[symbol] = expiry
                self.log_to_engine(
                    f"{symbol}: mapped {len(mapping)} contracts for {expiry} "
                    f"(lot {spec.lot_size}, step {spec.strike_step})."
                )

            # Backward-compatible aliases for legacy NIFTY diagnostics.
            self.strike_map = self.strike_maps["NIFTY"]
            self.active_expiry = self.active_expiries["NIFTY"]

            if not DHAN_CLIENT_ID or not DHAN_ACCESS_TOKEN:
                raise ValueError("Dhan Client ID or Access Token is missing in .env config.")
            context = DhanContext(client_id=DHAN_CLIENT_ID, access_token=DHAN_ACCESS_TOKEN)
            self.client = dhanhq(context)
            return True
        except Exception as exc:
            logger.error(
                "LiveFeed failed initialization: %s. Synthetic pricing is disabled; "
                "PAPER/LIVE execution remains blocked.",
                exc,
            )
            self.log_to_engine(
                f"Initialization failed: {exc}. Synthetic pricing is disabled and "
                "execution is blocked until the live feed recovers."
            )
            self.fallback_engaged = True
            return False

    def _build_quote_request(self) -> dict[str, list[int]]:
        option_ids: list[int] = []
        trade = self.engine.active_trade if self.engine is not None else None
        for symbol in sorted(self.registry.symbols):
            spec = self.registry.get(symbol)
            cache = self.caches.get(symbol)
            spot, _ = cache.get_spot()
            if spot <= 0.0:
                continue
            atm = int(round(spot / spec.strike_step) * spec.strike_step)
            ce_strikes = [atm - offset * spec.strike_step for offset in range(5)]
            pe_strikes = [atm + offset * spec.strike_step for offset in range(5)]
            if (
                trade is not None
                and trade.is_open
                and str(getattr(trade, "index_symbol", "NIFTY")).upper() == symbol
            ):
                ce_strikes.append(int(trade.strike_ce))
                pe_strikes.append(int(trade.strike_pe))
            mapping = self.strike_maps.get(symbol, {})
            option_ids.extend(
                mapping[(float(strike), "CE")]
                for strike in dict.fromkeys(ce_strikes)
                if (float(strike), "CE") in mapping
            )
            option_ids.extend(
                mapping[(float(strike), "PE")]
                for strike in dict.fromkeys(pe_strikes)
                if (float(strike), "PE") in mapping
            )
        return {
            "IDX_I": [
                self.registry.get(symbol).underlying_security_id
                for symbol in sorted(
                    self.registry.symbols,
                    key=lambda item: self.registry.get(item).underlying_security_id,
                )
            ],
            "NSE_FNO": list(dict.fromkeys(option_ids)),
        }

    def _apply_response(self, response: Mapping[str, object], now: datetime, latency_ms: int) -> None:
        segments = self._segments(response)
        index_rows = segments.get("IDX_I", {})
        if isinstance(index_rows, Mapping):
            by_security_id = {
                self.registry.get(symbol).underlying_security_id: symbol
                for symbol in self.registry.symbols
            }
            for raw_id, row in index_rows.items():
                if not isinstance(row, Mapping):
                    continue
                symbol = by_security_id.get(int(raw_id))
                price = float(row.get("last_price", 0.0) or 0.0)
                if symbol is None or price <= 0.0:
                    continue
                self.caches.get(symbol).update_spot(price, now)
                completed_candles.add_tick(spot_candle_key(symbol), now, price)

        option_rows = segments.get("NSE_FNO", {})
        if isinstance(option_rows, Mapping):
            for raw_id, row in option_rows.items():
                if not isinstance(row, Mapping):
                    continue
                identity = self.id_map.get(int(raw_id))
                if identity is None:
                    continue
                symbol, strike, option_type = identity
                ltp = float(row.get("last_price", 0.0) or 0.0)
                if ltp <= 0.0:
                    continue
                depth = row.get("depth", {})
                buys = depth.get("buy", []) if isinstance(depth, Mapping) else []
                sells = depth.get("sell", []) if isinstance(depth, Mapping) else []
                bid = float(buys[0].get("price", ltp) or ltp) if buys else ltp
                ask = float(sells[0].get("price", ltp) or ltp) if sells else ltp
                ohlc = row.get("ohlc", {})
                open_price = (
                    float(ohlc.get("open", ltp) or ltp)
                    if isinstance(ohlc, Mapping)
                    else ltp
                )
                volume = int(row.get("volume", 0) or 0)
                oi = int(row.get("oi", 0) or 0)
                cache = self.caches.get(symbol)
                cache.update_option(int(strike), option_type, {
                    "bid": bid,
                    "ask": ask,
                    "last": ltp,
                    "open": open_price,
                    "volume": volume,
                    "oi": oi,
                    "timestamp": now,
                })
                completed_candles.add_tick(
                    option_candle_key(symbol, strike, option_type),
                    now,
                    ltp,
                    volume=volume,
                    oi=oi,
                )

        for symbol in self.registry.symbols:
            self.caches.get(symbol).update_health(latency_ms=latency_ms)

    def _run(self) -> None:
        if not self._initialize_mapping():
            self._running = False
            return

        while self._running:
            try:
                now = datetime.now()
                request = self._build_quote_request()
                # First pass may contain only direct index quotes. The following
                # poll uses those spots to select the bounded option contracts.
                started = time.perf_counter()
                response = self._fetch_quotes(
                    request,
                    correlation_id=f"quote-{now.strftime('%Y%m%d-%H%M%S')}",
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                if response is not None and response.get("status") == "success":
                    self._apply_response(response, now, latency_ms)
                elif response is not None:
                    self.log_to_engine(f"Dhan quote query returned failure: {response}")
                time.sleep(5)
            except Exception as exc:
                logger.error("Error in LiveFeed polling cycle: %s", exc)
                self.fallback_engaged = True
                time.sleep(5)
