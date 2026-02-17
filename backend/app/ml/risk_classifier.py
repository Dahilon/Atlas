"""
Statistical risk tier classification using K-means clustering and Jenks Natural Breaks.

Replaces hardcoded thresholds with data-driven tier boundaries:
  critical / high / medium / low / info

Recomputes daily as data distribution shifts.
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


def classify_kmeans(scores: np.ndarray, k: int = 5) -> Tuple[List[float], Dict[str, Tuple[float, float]]]:
    """
    Use K-means clustering to find natural risk tier boundaries.

    Args:
        scores: 1D array of severity/risk scores (0-100)
        k: number of clusters (default 5 for our 5 tiers)

    Returns:
        (boundaries, tier_ranges)
        - boundaries: sorted list of k-1 threshold values
        - tier_ranges: {tier_name: (lower, upper)} for each tier
    """
    if len(scores) < k:
        # Not enough data — use uniform spacing
        step = 100.0 / k
        boundaries = [step * i for i in range(1, k)]
        tier_ranges = {}
        for i, name in enumerate(TIER_NAMES[:k]):
            lower = 0.0 if i == 0 else boundaries[i - 1]
            upper = 100.0 if i == k - 1 else boundaries[i]
            tier_ranges[name] = (lower, upper)
        return boundaries, tier_ranges

    X = scores.reshape(-1, 1)
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X)

    # Get cluster centroids and sort them
    centroids = sorted(kmeans.cluster_centers_.flatten())

    # Boundaries = midpoints between sorted centroids
    boundaries = []
    for i in range(len(centroids) - 1):
        boundaries.append((centroids[i] + centroids[i + 1]) / 2.0)

    # Build tier ranges
    tier_ranges = {}
    all_bounds = [0.0] + boundaries + [100.0]
    for i, name in enumerate(TIER_NAMES[:k]):
        tier_ranges[name] = (round(all_bounds[i], 2), round(all_bounds[i + 1], 2))

    return [round(b, 2) for b in boundaries], tier_ranges


def classify_jenks(scores: np.ndarray, k: int = 5) -> Tuple[List[float], Dict[str, Tuple[float, float]]]:
    """
    Use Jenks Natural Breaks optimization to find tier boundaries.

    Jenks minimizes within-class variance while maximizing between-class variance.
    Often produces better results than K-means for 1D classification.
    """
    if len(scores) < k:
        return classify_kmeans(scores, k)  # fallback

    breaks = jenkspy.jenks_breaks(scores.tolist(), n_classes=k)
    # breaks includes min and max: [min, b1, b2, ..., max]
    boundaries = breaks[1:-1]  # internal boundaries only

    tier_ranges = {}
    for i, name in enumerate(TIER_NAMES[:k]):
        lower = breaks[i]
        upper = breaks[i + 1]
        tier_ranges[name] = (round(lower, 2), round(upper, 2))

    return [round(b, 2) for b in boundaries], tier_ranges


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
        self.boundaries: List[float] = []
        self.tier_ranges: Dict[str, Tuple[float, float]] = {}
        self.all_scores: np.ndarray = np.array([])
        self.fitted_at: Optional[str] = None

    def fit(self, scores: List[float]) -> Dict:
        """
        Fit tier boundaries to current score distribution.
        Returns tier configuration dict.
        """
        arr = np.array([s for s in scores if s is not None and not np.isnan(s)])
        if len(arr) == 0:
            return {"method": self.method, "boundaries": [], "tier_ranges": {}}

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
        if not self.boundaries:
            # Not fitted yet — use default thresholds
            if score >= 80:
                tier = "critical"
            elif score >= 60:
                tier = "high"
            elif score >= 40:
                tier = "medium"
            elif score >= 20:
                tier = "low"
            else:
                tier = "info"
            return tier, 50.0

        tier = assign_tier(score, self.boundaries)
        percentile = compute_percentile(score, self.all_scores)
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
