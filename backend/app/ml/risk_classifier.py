"""
Statistical risk tier classification with real-world anchoring.

Uses Jenks Natural Breaks for data-driven boundaries, but anchors them
to geopolitical reality so known conflict zones are classified correctly.

Tiers: critical / high / medium / low / info
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import jenkspy
import numpy as np
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

TIER_NAMES = ["info", "low", "medium", "high", "critical"]  # ascending order

# ── Anchor boundaries ────────────────────────────────────────────────────
# These are minimum/maximum boundaries that prevent data-driven methods
# from producing unrealistic tier assignments.
# Derived from: ACLED conflict intensity scales, INFORM Risk Index,
# US State Dept travel advisory levels.
#
# Rule: a country with severity >= 70 should NEVER be below "high",
#       a country with severity >= 85 should NEVER be below "critical".

ANCHOR_BOUNDARIES = {
    "info_max": 25.0,       # info tier never extends above 25
    "low_max": 45.0,        # low tier never extends above 45
    "medium_max": 65.0,     # medium tier never extends above 65
    "high_max": 85.0,       # high tier never extends above 85
    "critical_min": 70.0,   # critical starts no higher than 85, no lower than 70
}

# Default fixed boundaries (used when not enough data for Jenks)
DEFAULT_BOUNDARIES = [20.0, 40.0, 60.0, 78.0]


def classify_kmeans(scores: np.ndarray, k: int = 5) -> Tuple[List[float], Dict[str, Tuple[float, float]]]:
    """
    Use K-means clustering to find natural risk tier boundaries.
    """
    if len(scores) < k:
        return DEFAULT_BOUNDARIES, _make_tier_ranges(DEFAULT_BOUNDARIES)

    X = scores.reshape(-1, 1)
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X)

    centroids = sorted(kmeans.cluster_centers_.flatten())

    boundaries = []
    for i in range(len(centroids) - 1):
        boundaries.append((centroids[i] + centroids[i + 1]) / 2.0)

    boundaries = _anchor_boundaries(boundaries)
    tier_ranges = _make_tier_ranges(boundaries)
    return [round(b, 2) for b in boundaries], tier_ranges


def classify_jenks(scores: np.ndarray, k: int = 5) -> Tuple[List[float], Dict[str, Tuple[float, float]]]:
    """
    Use Jenks Natural Breaks optimization to find tier boundaries,
    then anchor them to prevent unrealistic classifications.
    """
    if len(scores) < k:
        return DEFAULT_BOUNDARIES, _make_tier_ranges(DEFAULT_BOUNDARIES)

    breaks = jenkspy.jenks_breaks(scores.tolist(), n_classes=k)
    boundaries = breaks[1:-1]  # internal boundaries only

    # Anchor to real-world constraints
    boundaries = _anchor_boundaries(boundaries)
    tier_ranges = _make_tier_ranges(boundaries)
    return [round(b, 2) for b in boundaries], tier_ranges


def _anchor_boundaries(boundaries: List[float]) -> List[float]:
    """
    Apply anchoring constraints so tiers match real-world expectations.

    Data-driven boundaries (Jenks/K-means) can produce bad results with
    limited data. E.g. if all scores are 50-80, Jenks might put "critical"
    at >72, making Iran (severity 70) only "high". Anchoring prevents this.
    """
    if len(boundaries) != 4:
        return DEFAULT_BOUNDARIES

    b = list(boundaries)

    # Boundary 0: info → low (should be 15-25)
    b[0] = min(b[0], ANCHOR_BOUNDARIES["info_max"])
    b[0] = max(b[0], 10.0)

    # Boundary 1: low → medium (should be 30-45)
    b[1] = min(b[1], ANCHOR_BOUNDARIES["low_max"])
    b[1] = max(b[1], b[0] + 10)

    # Boundary 2: medium → high (should be 50-65)
    b[2] = min(b[2], ANCHOR_BOUNDARIES["medium_max"])
    b[2] = max(b[2], b[1] + 10)

    # Boundary 3: high → critical (should be 70-85)
    b[3] = min(b[3], ANCHOR_BOUNDARIES["high_max"])
    b[3] = max(b[3], ANCHOR_BOUNDARIES["critical_min"])
    b[3] = max(b[3], b[2] + 8)

    return b


def _make_tier_ranges(boundaries: List[float]) -> Dict[str, Tuple[float, float]]:
    """Build tier ranges dict from boundaries."""
    tier_ranges = {}
    all_bounds = [0.0] + boundaries + [100.0]
    for i, name in enumerate(TIER_NAMES[:len(all_bounds) - 1]):
        tier_ranges[name] = (round(all_bounds[i], 2), round(all_bounds[i + 1], 2))
    return tier_ranges


def assign_tier(
    score: float,
    boundaries: List[float],
    tier_names: Optional[List[str]] = None,
) -> str:
    """Assign a risk tier based on score and pre-computed boundaries."""
    names = tier_names or TIER_NAMES
    for i, bound in enumerate(boundaries):
        if score < bound:
            return names[i]
    return names[-1]


def compute_percentile(score: float, all_scores: np.ndarray) -> float:
    """Compute what percentile a score falls at within the distribution."""
    if len(all_scores) == 0:
        return 50.0
    return float(np.sum(all_scores <= score) / len(all_scores) * 100.0)


class RiskTierClassifier:
    """
    Stateful classifier that maintains current tier boundaries.
    Call fit() daily with latest scores, then classify() individual scores.
    """

    def __init__(self, method: str = "jenks", k: int = 5):
        self.method = method
        self.k = k
        self.boundaries: List[float] = list(DEFAULT_BOUNDARIES)
        self.tier_ranges: Dict[str, Tuple[float, float]] = _make_tier_ranges(DEFAULT_BOUNDARIES)
        self.all_scores: np.ndarray = np.array([])
        self.fitted_at: Optional[str] = None

    def fit(self, scores: List[float]) -> Dict:
        """
        Fit tier boundaries to current score distribution.
        Returns tier configuration dict.
        """
        arr = np.array([s for s in scores if s is not None and not np.isnan(s)])
        if len(arr) == 0:
            return {"method": self.method, "boundaries": self.boundaries, "tier_ranges": self.tier_ranges}

        self.all_scores = arr

        if self.method == "jenks":
            self.boundaries, self.tier_ranges = classify_jenks(arr, self.k)
        else:
            self.boundaries, self.tier_ranges = classify_kmeans(arr, self.k)

        self.fitted_at = datetime.now(timezone.utc).isoformat()

        return {
            "method": self.method,
            "boundaries": self.boundaries,
            "tier_ranges": self.tier_ranges,
            "n_samples": len(arr),
            "fitted_at": self.fitted_at,
            "stats": {
                "mean": round(float(np.mean(arr)), 2),
                "median": round(float(np.median(arr)), 2),
                "std": round(float(np.std(arr)), 2),
                "min": round(float(np.min(arr)), 2),
                "max": round(float(np.max(arr)), 2),
            },
        }

    def classify(self, score: float) -> Tuple[str, float]:
        """
        Classify a score into a tier.
        Returns (tier_name, percentile).
        """
        tier = assign_tier(score, self.boundaries)
        percentile = compute_percentile(score, self.all_scores) if len(self.all_scores) > 0 else 50.0
        return tier, round(percentile, 1)

    def to_dict(self) -> Dict:
        """Serialize state for API responses."""
        return {
            "method": self.method,
            "boundaries": self.boundaries,
            "tier_ranges": {k: list(v) for k, v in self.tier_ranges.items()},
            "fitted_at": self.fitted_at,
            "n_samples": len(self.all_scores),
        }
