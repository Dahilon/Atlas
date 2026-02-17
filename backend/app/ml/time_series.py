"""
Time series analysis: EWMA baselines and STL decomposition.

- EWMA: Exponentially Weighted Moving Average for smoother baselines
- STL: Seasonal-Trend decomposition using Loess (trend + seasonal + residual)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DecompositionResult:
    """STL decomposition components."""
    trend: List[float]
    seasonal: List[float]
    residual: List[float]
    dates: List[str]
    seasonal_strength: float  # 0-1, how strong the seasonal pattern is

    def to_dict(self) -> Dict:
        return {
            "trend": [round(v, 4) if not np.isnan(v) else None for v in self.trend],
            "seasonal": [round(v, 4) if not np.isnan(v) else None for v in self.seasonal],
            "residual": [round(v, 4) if not np.isnan(v) else None for v in self.residual],
            "dates": self.dates,
            "seasonal_strength": round(self.seasonal_strength, 4),
        }


def compute_ewma(
    values: List[float],
    alpha: float = 0.3,
) -> List[float]:
    """
    Compute Exponentially Weighted Moving Average.

    Alpha controls smoothing:
      - Higher alpha (0.5-0.9): more weight on recent values, faster response
      - Lower alpha (0.1-0.3): smoother, less reactive to noise
    """
    if not values:
        return []

    series = pd.Series(values)
    ewma = series.ewm(alpha=alpha, adjust=False).mean()
    return ewma.tolist()


def decompose_stl(
    values: List[float],
    dates: Optional[List[str]] = None,
    period: int = 7,
) -> Optional[DecompositionResult]:
    """
    STL decomposition of time series into trend + seasonal + residual.

    Args:
        values: time series values (daily)
        dates: optional date strings for labeling
        period: seasonal period (7 = weekly)

    Returns:
        DecompositionResult or None if insufficient data
    """
    if len(values) < period * 2:
        logger.debug("Not enough data for STL: %d < %d", len(values), period * 2)
        return None

    try:
        from statsmodels.tsa.seasonal import STL

        series = pd.Series(values, dtype=float)
        # Fill any NaN with forward fill
        series = series.ffill().bfill()

        stl = STL(series, period=period, robust=True)
        result = stl.fit()

        trend = result.trend.values.tolist()
        seasonal = result.seasonal.values.tolist()
        residual = result.resid.values.tolist()

        # Seasonal strength: 1 - Var(residual) / Var(seasonal + residual)
        var_resid = np.var(residual)
        var_seas_resid = np.var([s + r for s, r in zip(seasonal, residual)])
        if var_seas_resid > 0:
            seasonal_strength = max(0.0, 1.0 - var_resid / var_seas_resid)
        else:
            seasonal_strength = 0.0

        date_labels = dates if dates else [str(i) for i in range(len(values))]

        return DecompositionResult(
            trend=trend,
            seasonal=seasonal,
            residual=residual,
            dates=date_labels[:len(values)],
            seasonal_strength=seasonal_strength,
        )
    except Exception as e:
        logger.warning("STL decomposition failed: %s", e)
        return None


def detect_anomalies_from_residual(
    residuals: List[float],
    threshold: float = 2.0,
) -> List[bool]:
    """
    Flag anomalies based on STL residual component.

    An observation is anomalous if its residual exceeds threshold × MAD
    (Median Absolute Deviation).
    """
    arr = np.array(residuals)
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))

    if mad == 0:
        return [False] * len(residuals)

    # Scale MAD to standard deviation equivalent
    scaled_mad = mad * 1.4826
    z_scores = np.abs(arr - median) / scaled_mad

    return [bool(z > threshold) for z in z_scores]
