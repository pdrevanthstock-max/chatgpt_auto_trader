"""
Historical Data Loader
───────────────────────
Fetches CE + PE data from Dhan, aligns by timestamp,
splits into per-day buckets, and aggregates into N-minute candles.

§7.2 gotchas handled:
  - CE/PE fetched as two separate API calls, aligned by timestamp
  - Data split into per-day buckets (never span day boundary)
  - 1-min candles aggregated into configurable interval (default: 2-min)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

import pandas as pd
from loguru import logger

from core.models import Candle, PairedCandle, DayBucket
from core.exceptions import DataFetchError, InsufficientDataError
from data.dhan_client import DhanClient
from data.cache import DataCache


class HistoricalLoader:
    """
    Loads, aligns, and buckets historical CE/PE option data.
    This is the single entry point for all historical data needs.
    """

    def __init__(self, client: Optional[DhanClient] = None):
        self._client = client or DhanClient()
        self._cache = DataCache()

    def fetch_day_buckets(
        self,
        from_date: str,
        to_date: str,
        strike: str = "ATM",
        interval_minutes: int = 2,
    ) -> List[DayBucket]:
        """
        Fetch historical data and return per-day buckets of aligned
        CE+PE candles aggregated to the specified interval.

        Args:
            from_date: "YYYY-MM-DD"
            to_date: "YYYY-MM-DD"
            strike: "ATM", "ATM+1", etc.
            interval_minutes: aggregate 1-min candles into N-min (default 2)

        Returns:
            List of DayBucket, one per trading day, each containing
            aligned PairedCandle objects at the specified interval.
        """
        cache_key = f"{from_date}_{to_date}_{strike}_{interval_minutes}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for {cache_key} — {len(cached)} day buckets")
            return cached

        # §7.2 gotcha #3: Fetch CE and PE as separate calls
        logger.info(f"Fetching CE data: {from_date} to {to_date}, strike={strike}")
        ce_raw = self._client.get_expired_options_data(
            option_type="CALL",
            from_date=from_date,
            to_date=to_date,
            strike=strike,
            interval=1,  # Always fetch 1-min, aggregate ourselves
        )

        logger.info(f"Fetching PE data: {from_date} to {to_date}, strike={strike}")
        pe_raw = self._client.get_expired_options_data(
            option_type="PUT",
            from_date=from_date,
            to_date=to_date,
            strike=strike,
            interval=1,
        )

        # Parse raw responses into DataFrames
        ce_df = self._parse_response(ce_raw, "CE")
        pe_df = self._parse_response(pe_raw, "PE")

        if ce_df.empty or pe_df.empty:
            raise InsufficientDataError(
                f"No data returned for {from_date} to {to_date}. "
                f"CE rows: {len(ce_df)}, PE rows: {len(pe_df)}"
            )

        # §7.2 gotcha #3: Align by matching timestamps
        aligned = self._align_by_timestamp(ce_df, pe_df)
        logger.info(f"Aligned {len(aligned)} candle pairs")

        # §7.2 gotcha #2: Split into per-day buckets
        daily = self._split_into_days(aligned, strike)

        # Aggregate into N-minute candles if needed
        if interval_minutes > 1:
            daily = [
                self._aggregate_candles(bucket, interval_minutes)
                for bucket in daily
            ]

        logger.info(f"Produced {len(daily)} day buckets")

        # Cache results
        self._cache.put(cache_key, daily)

        return daily

    def _parse_response(self, raw: Dict, leg: str) -> pd.DataFrame:
        """
        Parse Dhan API response into a DataFrame.
        Handles nested format: {"data": {"ce": {"open": [...], ...}}}
        """
        def get_list_field(d: Dict, keys: List[str], target_len: int) -> List:
            for k in keys:
                v = d.get(k)
                if isinstance(v, list) and len(v) == target_len:
                    return v
            return [0] * target_len

        try:
            # Check for nested data dict containing "ce" or "pe"
            if "data" in raw and isinstance(raw["data"], dict):
                leg_key = leg.lower()
                if leg_key in raw["data"]:
                    leg_data = raw["data"][leg_key]
                    if isinstance(leg_data, dict) and "open" in leg_data and leg_data["open"]:
                        ts = leg_data.get("timestamp", leg_data.get("start_Time", []))
                        if not ts:
                            return pd.DataFrame()
                        
                        # Convert unix timestamps to timezone-naive IST
                        if isinstance(ts[0], (int, float)):
                            timestamps = pd.to_datetime(ts, unit="s").tz_localize("UTC").tz_convert("Asia/Kolkata").tz_localize(None)
                        else:
                            timestamps = pd.to_datetime(ts)
                            
                        target_len = len(leg_data["open"])
                        volume = get_list_field(leg_data, ["volume"], target_len)
                        oi = get_list_field(leg_data, ["oi", "open_interest"], target_len)

                        df = pd.DataFrame({
                            "timestamp": timestamps,
                            "open": leg_data["open"],
                            "high": leg_data["high"],
                            "low": leg_data["low"],
                            "close": leg_data["close"],
                            "volume": volume,
                            "oi": oi,
                        })
                        return df

            # Fallback to direct raw format
            # Format 1: {"open": [...], "high": [...], ...}
            if "open" in raw:
                ts = raw.get("timestamp", raw.get("start_Time", []))
                if not ts:
                    return pd.DataFrame()
                if isinstance(ts[0], (int, float)):
                    timestamps = pd.to_datetime(ts, unit="s").tz_localize("UTC").tz_convert("Asia/Kolkata").tz_localize(None)
                else:
                    timestamps = pd.to_datetime(ts)
                
                target_len = len(raw["open"])
                volume = get_list_field(raw, ["volume"], target_len)
                oi = get_list_field(raw, ["oi", "open_interest"], target_len)

                df = pd.DataFrame({
                    "timestamp": timestamps,
                    "open": raw["open"],
                    "high": raw["high"],
                    "low": raw["low"],
                    "close": raw["close"],
                    "volume": volume,
                    "oi": oi,
                })
                return df

            # Format 2: {"data": {"open": [...], ...}}
            if "data" in raw and isinstance(raw["data"], dict) and "open" in raw["data"]:
                data = raw["data"]
                ts = data.get("timestamp", data.get("start_Time", []))
                if not ts:
                    return pd.DataFrame()
                if isinstance(ts[0], (int, float)):
                    timestamps = pd.to_datetime(ts, unit="s").tz_localize("UTC").tz_convert("Asia/Kolkata").tz_localize(None)
                else:
                    timestamps = pd.to_datetime(ts)
                
                target_len = len(data["open"])
                volume = get_list_field(data, ["volume"], target_len)
                oi = get_list_field(data, ["oi", "open_interest"], target_len)

                df = pd.DataFrame({
                    "timestamp": timestamps,
                    "open": data["open"],
                    "high": data["high"],
                    "low": data["low"],
                    "close": data["close"],
                    "volume": volume,
                    "oi": oi,
                })
                return df

            # Format 3: list of candle dicts
            if isinstance(raw.get("data"), list):
                df = pd.DataFrame(raw["data"])
                if "start_Time" in df.columns:
                    df.rename(columns={"start_Time": "timestamp"}, inplace=True)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                if not df.empty and isinstance(df["timestamp"].iloc[0], (int, float)):
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
                return df

            logger.warning(f"Unexpected {leg} response format. Keys: {list(raw.keys())}")
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Failed to parse {leg} response: {e}")
            return pd.DataFrame()

    def _align_by_timestamp(
        self, ce_df: pd.DataFrame, pe_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        §7.2 gotcha #3: Align CE and PE by exact timestamp match.
        Only timestamps present in BOTH datasets are kept.
        """
        merged = pd.merge(
            ce_df, pe_df,
            on="timestamp",
            suffixes=("_ce", "_pe"),
            how="inner",
        )

        if len(merged) == 0:
            raise InsufficientDataError(
                "No overlapping timestamps between CE and PE data. "
                f"CE range: {ce_df['timestamp'].min()} to {ce_df['timestamp'].max()}, "
                f"PE range: {pe_df['timestamp'].min()} to {pe_df['timestamp'].max()}"
            )

        return merged.sort_values("timestamp").reset_index(drop=True)

    def _split_into_days(
        self, aligned: pd.DataFrame, strike: str
    ) -> List[DayBucket]:
        """
        §7.2 gotcha #2: Split into per-day buckets.
        A % change calculation must NEVER span a day boundary,
        because strike="ATM" resolves to different real contracts each day.
        """
        aligned["date"] = aligned["timestamp"].dt.date
        buckets = []

        for date_val, group in aligned.groupby("date"):
            candles = []
            for _, row in group.iterrows():
                pc = PairedCandle(
                    timestamp=row["timestamp"].to_pydatetime(),
                    strike=0,  # ATM — actual strike unknown from this API
                    ce_open=float(row["open_ce"]),
                    ce_high=float(row["high_ce"]),
                    ce_low=float(row["low_ce"]),
                    ce_close=float(row["close_ce"]),
                    ce_volume=int(row.get("volume_ce", 0)),
                    pe_open=float(row["open_pe"]),
                    pe_high=float(row["high_pe"]),
                    pe_low=float(row["low_pe"]),
                    pe_close=float(row["close_pe"]),
                    pe_volume=int(row.get("volume_pe", 0)),
                )
                candles.append(pc)

            bucket = DayBucket(
                date=datetime.combine(date_val, datetime.min.time()),
                strike=0,
                candles=candles,
            )
            buckets.append(bucket)

        return sorted(buckets, key=lambda b: b.date)

    def _aggregate_candles(
        self, bucket: DayBucket, interval_minutes: int
    ) -> DayBucket:
        """
        Aggregate 1-min candles into N-min candles.
        The user specified 2-minute candles but Dhan API only offers 1, 5, 15, 25, 60.
        So we fetch 1-min and aggregate here.
        """
        if not bucket.candles or interval_minutes <= 1:
            return bucket

        aggregated = []
        group: List[PairedCandle] = []

        for candle in bucket.candles:
            group.append(candle)

            if len(group) >= interval_minutes:
                agg = self._merge_candle_group(group)
                aggregated.append(agg)
                group = []

        # Handle remaining candles (partial last group)
        if group:
            agg = self._merge_candle_group(group)
            aggregated.append(agg)

        return DayBucket(
            date=bucket.date,
            strike=bucket.strike,
            candles=aggregated,
        )

    @staticmethod
    def _merge_candle_group(group: List[PairedCandle]) -> PairedCandle:
        """Merge a list of 1-min candles into one aggregated candle."""
        return PairedCandle(
            timestamp=group[0].timestamp,  # use first candle's timestamp
            strike=group[0].strike,
            ce_open=group[0].ce_open,
            ce_high=max(c.ce_high for c in group),
            ce_low=min(c.ce_low for c in group),
            ce_close=group[-1].ce_close,
            ce_volume=sum(c.ce_volume for c in group),
            pe_open=group[0].pe_open,
            pe_high=max(c.pe_high for c in group),
            pe_low=min(c.pe_low for c in group),
            pe_close=group[-1].pe_close,
            pe_volume=sum(c.pe_volume for c in group),
        )
