"""
Multi-method anomaly detection ensemble.

Methods:
  1. IQR (Interquartile Range) — robust for skewed distributions
  2. Isolation Forest — multi-variate (event_count × sentiment × severity)
  3. CUSUM — cumulative sum for drift detection (slow escalation)

Ensemble: require ≥2 methods to agree for high-confidence spike detection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


@dataclass
class AnomalyResult:
    """Result of multi-method anomaly detection for a single observation."""
    is_anomaly: bool  # ensemble decision (≥2 methods agree)
    anomaly_score: float  # 0-1 composite score
    methods_flagged: List[str]  # which methods flagged this
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "is_anomaly": self.is_anomaly,
            "anomaly_score": round(self.anomaly_score, 4),
            "methods_flagged": self.methods_flagged,
            "details": self.details,
        }


# ── IQR Method ────────────────────────────────────────────────────────────

def detect_iqr(
    values: List[float],
    multiplier: float = 1.5,
) -> List[bool]:
    """
    IQR-based outlier detection.

    An observation is an outlier if:
      value < Q1 - multiplier × IQR  OR  value > Q3 + multiplier × IQR
    """
    if len(values) < 4:
        return [False] * len(values)

    arr = np.array(values)
    q1 = np.percentile(arr, 25)
    q3 = np.percentile(arr, 75)
    iqr = q3 - q1

    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr

    return [bool(v < lower_bound or v > upper_bound) for v in values]


# ── Isolation Forest (Multi-variate) ─────────────────────────────────────

def detect_isolation_forest(
    features: np.ndarray,
    contamination: float = 0.1,
) -> Tuple[List[bool], List[float]]:
    """
    Isolation Forest for multi-variate anomaly detection.

    Args:
        features: 2D array of shape (n_samples, n_features)
                  e.g., columns = [event_count, sentiment, severity]
        contamination: expected fraction of anomalies

    Returns:
        (is_anomaly_list, anomaly_scores)
        anomaly_scores: lower = more anomalous (scikit-learn convention)
    """
    if len(features) < 10:
        return [False] * len(features), [0.0] * len(features)

    clf = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100,
    )
    predictions = clf.fit_predict(features)
    scores = clf.decision_function(features)

    # predictions: 1 = normal, -1 = anomaly
    is_anomaly = [bool(p == -1) for p in predictions]
    # Normalize scores to 0-1 (more anomalous = higher score)
    min_s, max_s = scores.min(), scores.max()
    if max_s > min_s:
        norm_scores = [1.0 - float((s - min_s) / (max_s - min_s)) for s in scores]
    else:
        norm_scores = [0.5] * len(scores)

    return is_anomaly, norm_scores


# ── CUSUM (Cumulative Sum) ───────────────────────────────────────────────

def detect_cusum(
    values: List[float],
    threshold: float = 5.0,
    drift: float = 0.5,
) -> Tuple[List[bool], List[float]]:
    """
    CUSUM (Cumulative Sum) for detecting sustained level changes.

    Detects when the process mean has shifted — useful for slow-building
    crises that don't show up as single spikes.

    Args:
        values: time series values
        threshold: CUSUM threshold (h) for signaling change
        drift: allowable drift (k) before accumulating

    Returns:
        (is_alert_list, cusum_scores)
    """
    if len(values) < 5:
        return [False] * len(values), [0.0] * len(values)

    arr = np.array(values, dtype=float)
    mean = np.mean(arr)

    # Upper and lower CUSUM
    s_pos = np.zeros(len(arr))
    s_neg = np.zeros(len(arr))
    alerts = [False] * len(arr)
    scores = [0.0] * len(arr)

    for i in range(1, len(arr)):
        s_pos[i] = max(0.0, s_pos[i - 1] + (arr[i] - mean) - drift)
        s_neg[i] = max(0.0, s_neg[i - 1] - (arr[i] - mean) - drift)
        scores[i] = float(max(s_pos[i], s_neg[i]))
        if s_pos[i] > threshold or s_neg[i] > threshold:
            alerts[i] = True

    return alerts, scores


# ── Ensemble ──────────────────────────────────────────────────────────────

def detect_anomalies_ensemble(
    event_counts: List[float],
    sentiments: Optional[List[float]] = None,
    severities: Optional[List[float]] = None,
    min_agreement: int = 2,
) -> List[AnomalyResult]:
    """
    Run all three anomaly detection methods and combine results.

    Requires at least `min_agreement` methods to agree before flagging
    as anomalous (default: 2 of 3).

    Args:
        event_counts: daily event counts (required)
        sentiments: daily average sentiment scores (optional)
        severities: daily severity indices (optional)

    Returns:
        List of AnomalyResult, one per observation
    """
    n = len(event_counts)
    if n == 0:
        return []

    # Method 1: IQR on event counts
    iqr_flags = detect_iqr(event_counts)

    # Method 2: Isolation Forest (multi-variate if available)
    features_list = [event_counts]
    if sentiments and len(sentiments) == n:
        features_list.append(sentiments)
    if severities and len(severities) == n:
        features_list.append(severities)

    feature_matrix = np.column_stack(features_list)
    iso_flags, iso_scores = detect_isolation_forest(feature_matrix)

    # Method 3: CUSUM on event counts
    cusum_flags, cusum_scores = detect_cusum(event_counts)

    # Combine
    results = []
    for i in range(n):
        methods = []
        if iqr_flags[i]:
            methods.append("iqr")
        if iso_flags[i]:
            methods.append("isolation_forest")
        if cusum_flags[i]:
            methods.append("cusum")

        is_anomaly = len(methods) >= min_agreement

        # Composite score: average of method-specific scores
        component_scores = [iso_scores[i]]
        if cusum_scores[i] > 0:
            # Normalize CUSUM score
            max_cusum = max(cusum_scores) if max(cusum_scores) > 0 else 1.0
            component_scores.append(cusum_scores[i] / max_cusum)
        anomaly_score = float(np.mean(component_scores))
        if is_anomaly:
            anomaly_score = max(anomaly_score, 0.6)  # floor for confirmed anomalies

        results.append(AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score,
            methods_flagged=methods,
            details={
                "iqr": iqr_flags[i],
                "isolation_forest": iso_flags[i],
                "isolation_score": round(iso_scores[i], 4),
                "cusum": cusum_flags[i],
                "cusum_score": round(cusum_scores[i], 4),
            },
        ))

    return results
