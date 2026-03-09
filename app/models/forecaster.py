"""
ML-based trend forecaster.

Reads historical trend_snapshots from the SQLite database and fits a simple
linear regression per trend to project scores 7, 14, and 30 days forward.

When there aren't enough data points yet (< 3), it falls back to a heuristic
estimate based on the latest score and momentum label.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

from app.database import (
    get_all_trend_history,
    save_forecast,
    get_latest_forecasts,
)
from app.utils import cache


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_iso(ts: str) -> float:
    """Convert an ISO-8601 timestamp string to a Unix epoch float."""
    ts = ts.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def _linear_forecast(
    times: List[float], scores: List[float], horizon_hours: float
) -> float:
    """
    Fit a least-squares line to (time, score) and extrapolate by horizon_hours.
    Returns the projected score, clipped to [0, 100].
    """
    t = np.array(times, dtype=float)
    s = np.array(scores, dtype=float)

    # Normalise time to hours from the first observation
    t = (t - t[0]) / 3600.0

    # Simple linear regression: s = a + b*t
    b, a = np.polyfit(t, s, 1)  # b=slope, a=intercept

    t_future = t[-1] + horizon_hours
    projected = a + b * t_future
    return float(np.clip(projected, 0, 100))


def _r_squared(times: List[float], scores: List[float]) -> float:
    """Return R² as a confidence measure (0–1)."""
    if len(scores) < 2:
        return 0.5
    t = np.array(times, dtype=float)
    s = np.array(scores, dtype=float)
    t = (t - t[0]) / 3600.0
    b, a = np.polyfit(t, s, 1)
    s_hat = a + b * t
    ss_res = float(np.sum((s - s_hat) ** 2))
    ss_tot = float(np.sum((s - s.mean()) ** 2))
    if ss_tot < 1e-9:
        return 1.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _heuristic_forecast(
    current_score: int, momentum: str, horizon_days: int
) -> float:
    """Fallback when fewer than 3 data points are available."""
    rates = {'rising': 0.04, 'stable': 0.0, 'falling': -0.04}
    rate = rates.get(momentum, 0.0)
    projected = current_score * (1 + rate) ** horizon_days
    return float(np.clip(projected, 0, 100))


# ── Main forecasting function ─────────────────────────────────────────────────

def compute_forecasts() -> List[Dict[str, Any]]:
    """
    Compute and persist forecasts for every trend in the database.
    Returns a list of forecast dicts.
    """
    cache_key = 'forecasts_computed'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    history = get_all_trend_history(days=60)
    results: List[Dict[str, Any]] = []

    for trend_name, snapshots in history.items():
        if not snapshots:
            continue

        scores = [s['score'] for s in snapshots]
        times  = [_parse_iso(s['snapshot_at']) for s in snapshots]
        last   = snapshots[-1]
        current_score = scores[-1]

        n = len(scores)

        if n >= 3:
            f7  = _linear_forecast(times, scores, 7   * 24)
            f14 = _linear_forecast(times, scores, 14  * 24)
            f30 = _linear_forecast(times, scores, 30  * 24)
            confidence = round(_r_squared(times, scores), 3)
        else:
            # Heuristic fallback
            mom = last.get('momentum', 'stable')
            f7  = _heuristic_forecast(current_score, mom, 7)
            f14 = _heuristic_forecast(current_score, mom, 14)
            f30 = _heuristic_forecast(current_score, mom, 30)
            confidence = 0.40

        # Direction
        delta = f7 - current_score
        if delta > 3:
            direction = 'rising'
        elif delta < -3:
            direction = 'falling'
        else:
            direction = 'stable'

        forecast = {
            'trend_name':       trend_name,
            'current_score':    round(current_score, 1),
            'forecast_7d':      round(f7, 1),
            'forecast_14d':     round(f14, 1),
            'forecast_30d':     round(f30, 1),
            'direction':        direction,
            'confidence':       confidence,
            'data_points_used': n,
        }
        save_forecast(forecast)
        results.append(forecast)

    results.sort(key=lambda x: x['forecast_7d'], reverse=True)
    cache.set(cache_key, results, ttl=300)
    return results


def get_forecasts() -> List[Dict[str, Any]]:
    """
    Return cached or freshly computed forecasts.
    Falls back to the DB's persisted forecasts if computation fails.
    """
    try:
        return compute_forecasts()
    except Exception:
        return get_latest_forecasts()


def get_trend_forecast(trend_name: str) -> Dict[str, Any]:
    """Return the forecast for a single named trend."""
    forecasts = get_forecasts()
    for f in forecasts:
        if f['trend_name'].lower() == trend_name.lower():
            return f
    return {}


def trend_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Return the top N trends ranked by their 7-day forecast score,
    enriched with a 'heat' label (hot / warm / cool).
    """
    forecasts = get_forecasts()[:limit]
    for f in forecasts:
        score = f.get('forecast_7d', 0)
        if score >= 60:
            f['heat'] = 'hot'
        elif score >= 30:
            f['heat'] = 'warm'
        else:
            f['heat'] = 'cool'
    return forecasts
