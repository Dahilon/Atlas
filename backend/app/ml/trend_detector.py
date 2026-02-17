"""
Trend detection for country-level risk time series.

Methods:
  1. Linear regression (OLS) on 7-day and 30-day windows
  2. Mann-Kendall non-parametric trend test
  3. Classification: rising / stable / falling
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class TrendResult:
    """Result of trend analysis for a single time series."""
    direction: str  # "rising", "stable", "falling"
    slope: float  # regression slope (units per day)
    confidence: float  # R² value (0-1)
    p_value: float  # statistical significance
    mk_direction: Optional[str] = None  # Mann-Kendall direction
    mk_p_value: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "direction": self.direction,
            "slope": round(self.slope, 4),
            "confidence": round(self.confidence, 4),
            "p_value": round(self.p_value, 4),
            "mk_direction": self.mk_direction,
            "mk_p_value": round(self.mk_p_value, 4) if self.mk_p_value is not None else None,
        }


def mann_kendall_test(data: np.ndarray) -> Tuple[str, float, float]:
    """
    Mann-Kendall non-parametric trend test.

    Returns (direction, tau, p_value).
    - tau > 0: increasing trend
    - tau < 0: decreasing trend
    - tau ≈ 0: no trend
    """
    n = len(data)
    if n < 4:
        return "stable", 0.0, 1.0

    # Calculate S statistic
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = data[j] - data[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Variance of S
    var_s = n * (n - 1) * (2 * n + 5) / 18.0

    # Handle ties
    unique, counts = np.unique(data, return_counts=True)
    for t in counts[counts > 1]:
        var_s -= t * (t - 1) * (2 * t + 5) / 18.0

    if var_s <= 0:
        return "stable", 0.0, 1.0

    # Z-score
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0

    # Two-tailed p-value
    p_value = 2.0 * stats.norm.sf(abs(z))

    # Kendall's tau
    tau = s / (n * (n - 1) / 2.0)

    if p_value < 0.05:
        direction = "rising" if tau > 0 else "falling"
    else:
        direction = "stable"

    return direction, float(tau), float(p_value)


def detect_trend(
    values: List[float],
    slope_threshold: float = 0.5,
    min_points: int = 4,
) -> TrendResult:
    """
    Detect trend in a time series using linear regression + Mann-Kendall.

    Args:
        values: ordered time series values (oldest first)
        slope_threshold: minimum absolute slope to classify as rising/falling
        min_points: minimum data points required

    Returns:
        TrendResult with direction, slope, confidence, p-values
    """
    arr = np.array([v for v in values if v is not None and not np.isnan(v)])

    if len(arr) < min_points:
        return TrendResult(
            direction="stable", slope=0.0, confidence=0.0, p_value=1.0,
        )

    # Linear regression
    x = np.arange(len(arr), dtype=float)
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, arr)
    r_squared = r_value ** 2

    # Classify direction from regression
    if p_value < 0.1 and abs(slope) > slope_threshold:
        reg_direction = "rising" if slope > 0 else "falling"
    else:
        reg_direction = "stable"

    # Mann-Kendall test
    mk_dir, mk_tau, mk_p = mann_kendall_test(arr)

    # Combined decision: use MK if significant, else regression
    if mk_p < 0.05:
        direction = mk_dir
    else:
        direction = reg_direction

    return TrendResult(
        direction=direction,
        slope=float(slope),
        confidence=float(r_squared),
        p_value=float(p_value),
        mk_direction=mk_dir,
        mk_p_value=float(mk_p),
    )


def detect_trends_for_countries(
    data: Dict[str, List[float]],
    window: int = 7,
) -> Dict[str, TrendResult]:
    """
    Detect trends for multiple countries.

    Args:
        data: {country_code: [values ordered by date ascending]}
        window: number of recent points to analyze

    Returns:
        {country_code: TrendResult}
    """
    results = {}
    for country, values in data.items():
        recent = values[-window:] if len(values) > window else values
        results[country] = detect_trend(recent)
    return results
