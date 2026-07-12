import logging
import pandas as pd
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.settings import TradingConfig
from data.dhan_client import DhanClient
from core.models import Candle
from core.exceptions import InsufficientDataError

logger = logging.getLogger("AutoTrader")

class HistoricalDayData:
    """Holds all historical option contract candles for a single trading day."""
    def __init__(self, session_date: date) -> None:
        self.date: date = session_date
        self.timestamps: List[datetime] = []
        # Structure: { timestamp: { relative_strike: { "CE": Candle, "PE": Candle } } }
        self.candles: Dict[datetime, Dict[str, Dict[str, Candle]]] = {}

class HistoricalLoader:
    """Fetches and aligns historical multi-strike option candles from Dhan API."""
    def __init__(self) -> None:
        self.client = DhanClient()

    def fetch_historical_data(
        self,
        from_date: str,
        to_date: str,
        scan_range: int = 10,
        interval_minutes: int = 2
    ) -> List[HistoricalDayData]:
        """
        Fetches option data for all relative strikes (ATM, ITM1-N, OTM1-N)
        and groups them by trading day, with offline cache fallback.
        """
        from config.settings import DHAN_ACCESS_TOKEN, PROJECT_ROOT
        import json

        # Build relative strike labels
        strikes = ["ATM"]
        for i in range(1, scan_range + 1):
            strikes.append(f"ITM{i}")
            strikes.append(f"OTM{i}")

        use_offline_cache = False
        if not DHAN_ACCESS_TOKEN or len(DHAN_ACCESS_TOKEN) < 10:
            logger.info("DHAN_ACCESS_TOKEN is missing or invalid. Using offline cache fallback.")
            use_offline_cache = True

        if not use_offline_cache:
            try:
                logger.info(f"Preparing to fetch {len(strikes) * 2} option series for date range {from_date} to {to_date}")
                results = {}
                futures = {}
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    for strike in strikes:
                        for op_type in ["CALL", "PUT"]:
                            key = (strike, op_type)
                            futures[executor.submit(
                                self.client.get_expired_options_data,
                                option_type=op_type,
                                from_date=from_date,
                                to_date=to_date,
                                strike=strike,
                                interval=1 # Always fetch 1-minute data from Dhan API
                            )] = key

                    for future in as_completed(futures):
                        strike, op_type = futures[future]
                        try:
                            raw = future.result()
                            # Check if the API returned an authentication error
                            if isinstance(raw, dict) and raw.get("status") == "failure" and "Authentication" in raw.get("remarks", {}).get("error_message", ""):
                                raise ValueError("Invalid access token returned by API.")
                            df = self._parse_raw_df(raw, strike, op_type, interval_minutes)
                            if not df.empty:
                                results[(strike, op_type)] = df
                                logger.info(f"Loaded {len(df)} candles for {strike} {op_type}")
                            else:
                                logger.warning(f"No candles parsed for {strike} {op_type}")
                        except Exception as e:
                            logger.error(f"Error fetching data for {strike} {op_type}: {e}")

                if not results:
                    raise InsufficientDataError(f"No historical data returned for range {from_date} to {to_date}")
                
                return self._align_and_group(results, strikes)
            except Exception as e:
                logger.warning(f"Dhan API fetch failed ({e}). Falling back to offline cache...")
                use_offline_cache = True

        if use_offline_cache:
            cache_file = PROJECT_ROOT / "cache" / "cache_06883e782d7c16e4.json"
            if cache_file.exists():
                logger.info(f"Loading from offline cache file: {cache_file}")
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
                
                day_map = {}
                from_dt = pd.to_datetime(from_date).date()
                to_dt = pd.to_datetime(to_date).date()
                
                for item in cache_data:
                    item_date = pd.to_datetime(item["date"]).date()
                    if from_dt <= item_date <= to_dt:
                        day_data = HistoricalDayData(item_date)
                        for c_data in item.get("candles", []):
                            ts = pd.to_datetime(c_data["ts"])
                            day_data.timestamps.append(ts)
                            day_data.candles[ts] = {"ATM": {}}
                            
                            # Reconstruct CE and PE candles
                            # Anchor base strike to Nifty index level of June 2026 (24300)
                            ce_candle = Candle(
                                timestamp=ts,
                                open=c_data["co"],
                                high=c_data["ch"],
                                low=c_data["cl"],
                                close=c_data["cc"],
                                volume=int(c_data["cv"]),
                                oi=0,
                                strike=24300.0,
                                spot=24300.0 + c_data["cc"] - c_data["pc"]
                            )
                            pe_candle = Candle(
                                timestamp=ts,
                                open=c_data["po"],
                                high=c_data["ph"],
                                low=c_data["pl"],
                                close=c_data["pc"],
                                volume=int(c_data["pv"]),
                                oi=0,
                                strike=24300.0,
                                spot=24300.0 + c_data["cc"] - c_data["pc"]
                            )
                            day_data.candles[ts]["ATM"]["CE"] = ce_candle
                            day_data.candles[ts]["ATM"]["PE"] = pe_candle
                        
                        day_map[item_date] = day_data
                
                sorted_days = [day_map[d] for d in sorted(day_map.keys())]
                if sorted_days:
                    logger.info(f"Offline cache loaded {len(sorted_days)} trading days successfully.")
                    return sorted_days
                
            raise InsufficientDataError(
                f"No offline cache or live data available for range {from_date} to {to_date}."
            )

    def _parse_raw_df(self, raw: Dict[str, Any], strike: str, op_type: str, interval_minutes: int) -> pd.DataFrame:
        """Parse raw response from expired_options_data API endpoint."""
        try:
            # Structurally parse Dhan API nested format
            # Format: {"data": {"data": {"ce": {"open": [...], ...}}}}
            # or {"data": {"data": {"pe": {"open": [...], ...}}}}
            d1 = raw.get("data", {})
            d2 = d1.get("data", {})
            leg_key = "ce" if op_type == "CALL" else "pe"
            leg_data = d2.get(leg_key)

            if not leg_data or not isinstance(leg_data, dict) or "open" not in leg_data:
                # Fallback to direct check
                leg_data = d1.get(leg_key)
                if not leg_data or not isinstance(leg_data, dict) or "open" not in leg_data:
                    return pd.DataFrame()

            ts = leg_data.get("timestamp", leg_data.get("start_Time", []))
            if not ts:
                return pd.DataFrame()

            # Timezone-naive IST timestamps
            if isinstance(ts[0], (int, float)):
                timestamps = pd.to_datetime(ts, unit="s").tz_localize("UTC").tz_convert("Asia/Kolkata").tz_localize(None)
            else:
                timestamps = pd.to_datetime(ts)

            target_len = len(leg_data["open"])
            
            def get_list_field(d: Dict, keys: List[str], target_len: int) -> List:
                for k in keys:
                    v = d.get(k)
                    if isinstance(v, list) and len(v) == target_len:
                        return v
                return [0] * target_len

            volume = get_list_field(leg_data, ["volume"], target_len)
            oi = get_list_field(leg_data, ["oi", "open_interest"], target_len)
            strike_list = get_list_field(leg_data, ["strike"], target_len)
            spot_list = get_list_field(leg_data, ["spot"], target_len)

            df = pd.DataFrame({
                "timestamp": timestamps,
                "open": leg_data["open"],
                "high": leg_data["high"],
                "low": leg_data["low"],
                "close": leg_data["close"],
                "volume": volume,
                "oi": oi,
                "strike": strike_list,
                "spot": spot_list
            })

            # Resample to multi-minute interval if required
            if interval_minutes > 1:
                df.set_index("timestamp", inplace=True)
                df = df.resample(f"{interval_minutes}Min").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "oi": "last",
                    "strike": "first",
                    "spot": "last"
                }).dropna().reset_index()

            return df
        except Exception as e:
            logger.error(f"Error parsing raw {strike} {op_type} data: {e}")
            return pd.DataFrame()

    def _align_and_group(self, results: Dict[tuple[str, str], pd.DataFrame], strikes: List[str]) -> List[HistoricalDayData]:
        """Align all series on timestamp, group by date."""
        # Find all unique timestamps across all loaded series
        all_timestamps = set()
        for df in results.values():
            all_timestamps.update(df["timestamp"].tolist())
        
        sorted_ts = sorted(list(all_timestamps))
        
        # Map timestamp to index in the DataFrame for fast lookup
        ts_lookups = {}
        for key, df in results.items():
            ts_lookups[key] = df.set_index("timestamp").to_dict(orient="index")

        # Group by day
        day_map: Dict[date, HistoricalDayData] = {}
        
        for ts in sorted_ts:
            d = ts.date()
            if d not in day_map:
                day_map[d] = HistoricalDayData(d)
            
            day_data = day_map[d]
            day_data.timestamps.append(ts)
            day_data.candles[ts] = {}
            
            for strike in strikes:
                day_data.candles[ts][strike] = {}
                
                # CE
                ce_candle = self._get_candle_from_lookup(ts_lookups.get((strike, "CALL")), ts)
                if ce_candle:
                    day_data.candles[ts][strike]["CE"] = ce_candle
                
                # PE
                pe_candle = self._get_candle_from_lookup(ts_lookups.get((strike, "PUT")), ts)
                if pe_candle:
                    day_data.candles[ts][strike]["PE"] = pe_candle

        # Filter out empty or incomplete days and sort
        sorted_days = []
        for d in sorted(day_map.keys()):
            day_data = day_map[d]
            # Verify we have candles in this day
            if len(day_data.timestamps) > 0:
                sorted_days.append(day_data)
                logger.info(f"Day session {d} aligned with {len(day_data.timestamps)} candles.")
                
        return sorted_days

    def _get_candle_from_lookup(self, lookup: Optional[Dict[datetime, Dict[str, Any]]], ts: datetime) -> Optional[Candle]:
        if not lookup or ts not in lookup:
            return None
        row = lookup[ts]
        return Candle(
            timestamp=ts,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=int(row.get("volume", 0)),
            oi=int(row.get("oi", 0)),
            strike=float(row.get("strike", 0.0)),
            spot=float(row.get("spot", 0.0))
        )
