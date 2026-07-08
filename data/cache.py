"""
Data Cache
───────────
Local JSON-based cache to avoid re-fetching the same date ranges.
Caches serialized DayBucket lists keyed by (date_range, strike, interval).
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from loguru import logger

from config.settings import CACHE_DIR
from core.models import DayBucket, PairedCandle


class DataCache:
    """Simple file-based cache for historical data."""

    def __init__(self, cache_dir: Path = None):
        self._dir = cache_dir or CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[List[DayBucket]]:
        """Retrieve cached day buckets, or None if not cached."""
        path = self._key_to_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Cache read failed for {key}: {e}")
            return None

    def put(self, key: str, buckets: List[DayBucket]) -> None:
        """Cache day buckets to disk."""
        path = self._key_to_path(key)
        try:
            data = self._serialize(buckets)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.debug(f"Cached {len(buckets)} day buckets to {path.name}")
        except Exception as e:
            logger.warning(f"Cache write failed for {key}: {e}")

    def clear(self) -> None:
        """Remove all cached files."""
        for f in self._dir.glob("*.json"):
            f.unlink()
        logger.info("Cache cleared")

    def _key_to_path(self, key: str) -> Path:
        """Hash key to a filename."""
        h = hashlib.md5(key.encode()).hexdigest()[:16]
        return self._dir / f"cache_{h}.json"

    @staticmethod
    def _serialize(buckets: List[DayBucket]) -> List[dict]:
        """Serialize DayBucket list to JSON-safe dicts."""
        result = []
        for bucket in buckets:
            candle_data = []
            for c in bucket.candles:
                candle_data.append({
                    "ts": c.timestamp.isoformat(),
                    "strike": c.strike,
                    "co": c.ce_open, "ch": c.ce_high,
                    "cl": c.ce_low, "cc": c.ce_close, "cv": c.ce_volume,
                    "po": c.pe_open, "ph": c.pe_high,
                    "pl": c.pe_low, "pc": c.pe_close, "pv": c.pe_volume,
                })
            result.append({
                "date": bucket.date.isoformat(),
                "strike": bucket.strike,
                "candles": candle_data,
            })
        return result

    @staticmethod
    def _deserialize(data: List[dict]) -> List[DayBucket]:
        """Deserialize JSON dicts back to DayBucket list."""
        buckets = []
        for item in data:
            candles = []
            for c in item["candles"]:
                candles.append(PairedCandle(
                    timestamp=datetime.fromisoformat(c["ts"]),
                    strike=c["strike"],
                    ce_open=c["co"], ce_high=c["ch"],
                    ce_low=c["cl"], ce_close=c["cc"], ce_volume=c["cv"],
                    pe_open=c["po"], pe_high=c["ph"],
                    pe_low=c["pl"], pe_close=c["pc"], pe_volume=c["pv"],
                ))
            buckets.append(DayBucket(
                date=datetime.fromisoformat(item["date"]),
                strike=item["strike"],
                candles=candles,
            ))
        return buckets
