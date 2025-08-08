"""dpi_gamma_heuristic.py

Light‑weight heuristic module that assigns a numeric *risk_score* and optional
flags to each document based on:

1. **DPI**
   * ≤ 96 → `LOW_DPI` (+10)
   * ≥ 600 → `HIGH_DPI` (+10)
   * missing → +2 (no flag)
2. **Gamma** (PNG `gAMA` chunk)
   * outside 0.40 – 0.60 → `GAMMA_OUT_OF_RANGE` (+10)
   * missing → +2 (no flag)
3. **GCS overwrite detection** – if `gcs.updated` is more than 1 minute after
   `gcs.time_created` we assume the object was replaced and add
   `OBJECT_OVERWRITTEN` (+15).

Returning structure
-------------------
```json
{
  "dpi_status":    "low|high|normal|unknown",
  "gamma_status":  "out_of_range|in_range|unknown",
  "risk_score":    <int>,
  "flags":         ["HIGH_DPI", "OBJECT_OVERWRITTEN", …]
}
```

Usage
-----
```python
from .dpi_gamma_heuristic import HeuristicChecker
risk = HeuristicChecker().evaluate(meta_dict)
```
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List


class HeuristicChecker:
    """Single‑method stateless scorer."""

    # DPI thresholds (px per inch)
    LOW_DPI_THRESHOLD:  int = 96
    HIGH_DPI_THRESHOLD: int = 600

    # Gamma acceptable band (for sRGB images gamma ≈ 0.45455)
    GAMMA_MIN: float = 0.40
    GAMMA_MAX: float = 0.60

    # Penalties when a metric is missing
    UNKNOWN_PENALTY: int = 2

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_dpi(meta: Dict[str, Any]) -> Tuple[float | None, str]:
        """Return average DPI and the key it came from."""
        if "PNG:dpi" in meta:
            try:
                x_dpi, y_dpi = meta["PNG:dpi"]
                return (float(x_dpi) + float(y_dpi)) / 2, "PNG:dpi"
            except Exception:  # noqa: BLE001
                pass
        return None, ""

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_gamma(meta: Dict[str, Any]) -> Tuple[float | None, str]:
        if "PNG:gamma" in meta:
            try:
                return float(meta["PNG:gamma"]), "PNG:gamma"
            except Exception:  # noqa: BLE001
                pass
        return None, ""

    # ------------------------------------------------------------------
    @staticmethod
    def _parse(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            # handle 2025-05-15T13:00:08.013000+00:00 or Z
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    @classmethod
    def evaluate(cls, meta: Dict[str, Any]) -> Dict[str, Any]:
        risk: int = 0
        flags: List[str] = []

        # DPI evaluation
        dpi, _ = cls._extract_dpi(meta)
        if dpi is None:
            dpi_status = "unknown"
            risk += cls.UNKNOWN_PENALTY
        elif dpi <= cls.LOW_DPI_THRESHOLD:
            dpi_status = "low"
            risk += 10
            flags.append("LOW_DPI")
        elif dpi >= cls.HIGH_DPI_THRESHOLD:
            dpi_status = "high"
            risk += 10
            flags.append("HIGH_DPI")
        else:
            dpi_status = "normal"

        # Gamma evaluation
        gamma, _ = cls._extract_gamma(meta)
        if gamma is None:
            gamma_status = "unknown"
            risk += cls.UNKNOWN_PENALTY
        elif not (cls.GAMMA_MIN <= gamma <= cls.GAMMA_MAX):
            gamma_status = "out_of_range"
            risk += 10
            flags.append("GAMMA_OUT_OF_RANGE")
        else:
            gamma_status = "in_range"

        # GCS overwrite check
        created = cls._parse(meta.get("gcs.time_created"))
        updated = cls._parse(meta.get("gcs.updated"))
        if created and updated and (updated - created).total_seconds() > 60:
            risk += 15
            flags.append("OBJECT_OVERWRITTEN")

        # ------------------------------------------------------------------
        return {
            "dpi_status": dpi_status,
            "gamma_status": gamma_status,
            "risk_score": risk,
            "flags": flags,
        }
