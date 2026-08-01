"""Transparent, bounded demonstration valuation models.

The estimates in this module are educational signals, not financial advice or
market quotes. Inputs are normalised defensively because public sports feeds can
contain missing, malformed, or unexpectedly large values.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MAX_VALUE_MILLIONS = 250.0

FEATURES = [
    "age_potential",
    "availability",
    "rating_signal",
    "goals_per_90",
    "assists_per_90",
    "defensive_actions_per_90",
    "clean_sheet_rate",
    "saves_per_90",
    "concession_control",
    "is_goalkeeper",
    "is_defender",
    "is_midfielder",
    "is_attacker",
]

_LIMITS = {
    "age": 45.0,
    "games": 80.0,
    "minutes": 6000.0,
    "rating": 10.0,
    "goals": 100.0,
    "assists": 100.0,
    "tackles": 500.0,
    "interceptions": 300.0,
    "clean_sheets": 60.0,
    "saves": 500.0,
    "conceded": 300.0,
}


def _bounded_number(
    value: Any,
    *,
    default: float = 0.0,
    minimum: float = 0.0,
    maximum: float,
) -> float:
    """Coerce a value to a finite number inside a deliberate model boundary."""
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return min(max(number, minimum), maximum)


def _stat(stats: dict[str, Any], key: str) -> float:
    return _bounded_number(stats.get(key), maximum=_LIMITS[key])


def _position(stats: dict[str, Any]) -> str:
    position = str(stats.get("position") or "").strip().lower()
    for role in ("goalkeeper", "defender", "midfielder", "attacker"):
        if role in position:
            return role
    return "unknown"


def per_90(value: Any, minutes: Any, maximum: float = 25.0) -> float:
    """Return a safe per-90 rate, capped to keep model inputs plausible."""
    safe_maximum = _bounded_number(maximum, default=25.0, minimum=0.0, maximum=1000.0)
    safe_value = _bounded_number(value, default=0.0, minimum=0.0, maximum=1_000_000.0)
    safe_minutes = _bounded_number(
        minutes, default=0.0, minimum=0.0, maximum=1_000_000.0
    )
    if safe_minutes <= 0 or safe_maximum <= 0:
        return 0.0
    return round(min((safe_value * 90.0) / safe_minutes, safe_maximum), 2)


def _has_season_data(stats: dict[str, Any]) -> bool:
    return _stat(stats, "games") > 0 or _stat(stats, "minutes") > 0


def _feature_values(stats: dict[str, Any]) -> dict[str, float]:
    age = _bounded_number(
        stats.get("age"), default=25.0, minimum=16.0, maximum=_LIMITS["age"]
    )
    games = _stat(stats, "games")
    minutes = _stat(stats, "minutes")
    rate_minutes = minutes or games * 75.0
    position = _position(stats)

    clean_sheet_rate = min(_stat(stats, "clean_sheets") / games, 1.0) if games else 0.0
    conceded_rate = per_90(_stat(stats, "conceded"), rate_minutes, maximum=6.0)
    return {
        "age_potential": max(0.0, 32.0 - age),
        "availability": min(max(games / 30.0, minutes / 2700.0), 1.0),
        "rating_signal": max(0.0, _stat(stats, "rating") - 6.0),
        "goals_per_90": per_90(_stat(stats, "goals"), rate_minutes, maximum=4.0),
        "assists_per_90": per_90(_stat(stats, "assists"), rate_minutes, maximum=4.0),
        "defensive_actions_per_90": per_90(
            _stat(stats, "tackles") + _stat(stats, "interceptions"),
            rate_minutes,
            maximum=20.0,
        ),
        "clean_sheet_rate": clean_sheet_rate,
        "saves_per_90": per_90(_stat(stats, "saves"), rate_minutes, maximum=15.0),
        "concession_control": (
            max(0.0, 3.0 - conceded_rate) if position == "goalkeeper" else 0.0
        ),
        "is_goalkeeper": float(position == "goalkeeper"),
        "is_defender": float(position == "defender"),
        "is_midfielder": float(position == "midfielder"),
        "is_attacker": float(position == "attacker"),
    }


def _positive(value: Any) -> float:
    """Round and constrain a model result to an explicit product range."""
    number = _bounded_number(value, maximum=MAX_VALUE_MILLIONS)
    return round(number, 2)


def calculate_value_heuristic(stats: dict[str, Any]) -> float:
    """Estimate value using position-aware rates, age, rating, and availability."""
    if not _has_season_data(stats):
        return 0.0

    features = _feature_values(stats)
    position = _position(stats)
    goals = features["goals_per_90"]
    assists = features["assists_per_90"]
    defensive_actions = features["defensive_actions_per_90"]

    if position == "goalkeeper":
        performance = (
            features["saves_per_90"] * 2.4
            + features["clean_sheet_rate"] * 10.0
            + features["concession_control"] * 3.0
        )
    elif position == "defender":
        performance = (
            defensive_actions * 2.0
            + goals * 10.0
            + assists * 8.0
            + features["clean_sheet_rate"] * 4.0
        )
    elif position == "midfielder":
        performance = goals * 14.0 + assists * 14.0 + defensive_actions * 1.2
    elif position == "attacker":
        performance = goals * 22.0 + assists * 14.0
    else:
        performance = (
            goals * 12.0
            + assists * 12.0
            + defensive_actions * 0.7
            + features["saves_per_90"] * 0.5
        )

    age = _bounded_number(
        stats.get("age"), default=25.0, minimum=16.0, maximum=_LIMITS["age"]
    )
    age_factor = max(0.45, 1.32 - max(age - 21.0, 0.0) * 0.04)
    availability_factor = 0.35 + features["availability"] * 0.65
    rating_bonus = features["rating_signal"] * 3.0
    return _positive(
        (1.5 + performance + rating_bonus) * age_factor * availability_factor
    )


_TRAINING_PLAYERS: tuple[tuple[dict[str, Any], float], ...] = (
    (
        {
            "age": 36,
            "position": "Goalkeeper",
            "games": 25,
            "minutes": 2250,
            "rating": 6.7,
            "saves": 70,
            "conceded": 38,
            "clean_sheets": 6,
        },
        7,
    ),
    (
        {
            "age": 31,
            "position": "Goalkeeper",
            "games": 34,
            "minutes": 3060,
            "rating": 7.1,
            "saves": 110,
            "conceded": 32,
            "clean_sheets": 12,
        },
        22,
    ),
    (
        {
            "age": 24,
            "position": "Goalkeeper",
            "games": 28,
            "minutes": 2520,
            "rating": 7.4,
            "saves": 95,
            "conceded": 24,
            "clean_sheets": 11,
        },
        48,
    ),
    (
        {
            "age": 34,
            "position": "Defender",
            "games": 24,
            "minutes": 1900,
            "rating": 6.7,
            "goals": 1,
            "assists": 1,
            "tackles": 40,
            "interceptions": 28,
            "clean_sheets": 6,
        },
        8,
    ),
    (
        {
            "age": 27,
            "position": "Defender",
            "games": 31,
            "minutes": 2700,
            "rating": 7.1,
            "goals": 2,
            "assists": 3,
            "tackles": 65,
            "interceptions": 41,
            "clean_sheets": 10,
        },
        30,
    ),
    (
        {
            "age": 21,
            "position": "Defender",
            "games": 29,
            "minutes": 2500,
            "rating": 7.4,
            "goals": 4,
            "assists": 5,
            "tackles": 72,
            "interceptions": 48,
            "clean_sheets": 12,
        },
        52,
    ),
    (
        {
            "age": 32,
            "position": "Midfielder",
            "games": 27,
            "minutes": 2100,
            "rating": 6.9,
            "goals": 4,
            "assists": 5,
            "tackles": 34,
            "interceptions": 19,
        },
        15,
    ),
    (
        {
            "age": 26,
            "position": "Midfielder",
            "games": 32,
            "minutes": 2600,
            "rating": 7.3,
            "goals": 9,
            "assists": 11,
            "tackles": 48,
            "interceptions": 25,
        },
        45,
    ),
    (
        {
            "age": 20,
            "position": "Midfielder",
            "games": 30,
            "minutes": 2400,
            "rating": 7.6,
            "goals": 11,
            "assists": 14,
            "tackles": 52,
            "interceptions": 29,
        },
        75,
    ),
    (
        {
            "age": 31,
            "position": "Attacker",
            "games": 28,
            "minutes": 2100,
            "rating": 7.0,
            "goals": 12,
            "assists": 5,
            "tackles": 8,
            "interceptions": 3,
        },
        30,
    ),
    (
        {
            "age": 25,
            "position": "Attacker",
            "games": 33,
            "minutes": 2700,
            "rating": 7.6,
            "goals": 24,
            "assists": 9,
            "tackles": 10,
            "interceptions": 4,
        },
        90,
    ),
    (
        {
            "age": 19,
            "position": "Attacker",
            "games": 29,
            "minutes": 2250,
            "rating": 7.8,
            "goals": 21,
            "assists": 12,
            "tackles": 14,
            "interceptions": 5,
        },
        110,
    ),
)


@lru_cache(maxsize=1)
def _demo_model():
    """Train a deterministic model whose input signals are all favorable."""
    frame = pd.DataFrame(
        [_feature_values(stats) for stats, _ in _TRAINING_PLAYERS],
        columns=FEATURES,
    )
    targets = [fee for _, fee in _TRAINING_PLAYERS]
    model = make_pipeline(
        StandardScaler(),
        Ridge(alpha=6.0, positive=True, solver="lbfgs", max_iter=10_000),
    )
    return model.fit(frame, targets)


def predict_value_ml(stats: dict[str, Any]) -> float:
    """Predict a bounded value from transparent, favorable engineered features."""
    if not _has_season_data(stats):
        return 0.0
    sample = pd.DataFrame([_feature_values(stats)], columns=FEATURES)
    return _positive(_demo_model().predict(sample)[0])


def calculate_context_value(stats: dict[str, Any]) -> float:
    """Apply transparent fictional contract, risk, and league context."""
    if not _has_season_data(stats):
        return 0.0

    performance_base = (
        calculate_value_heuristic(stats) * 0.55 + predict_value_ml(stats) * 0.45
    )
    league_strength = _bounded_number(
        stats.get("league_strength"),
        default=0.85,
        minimum=0.6,
        maximum=1.2,
    )
    selling_power = _bounded_number(
        stats.get("club_selling_power"),
        default=1.0,
        minimum=0.75,
        maximum=1.25,
    )
    contract_years = _bounded_number(
        stats.get("contract_years"),
        default=2.0,
        minimum=0.0,
        maximum=6.0,
    )
    contract_factor = 0.82 + min(contract_years, 5.0) * 0.06
    risk_factor = {
        "low": 1.02,
        "medium": 0.94,
        "high": 0.82,
    }.get(str(stats.get("injury_risk") or "").strip().lower(), 0.94)

    contextual = (
        performance_base
        * league_strength
        * selling_power
        * contract_factor
        * risk_factor
    )
    recent_fee = _bounded_number(stats.get("recent_fee"), maximum=MAX_VALUE_MILLIONS)
    if recent_fee > 0:
        contextual = contextual * 0.82 + recent_fee * 0.18
    return _positive(contextual)


def compare_methods(stats: dict[str, Any]) -> dict[str, float]:
    """Return three transparent educational valuation scenarios."""
    return {
        "Heuristic": calculate_value_heuristic(stats),
        "Demo ML": predict_value_ml(stats),
        "Context": calculate_context_value(stats),
    }


def valuation_confidence(
    stats: dict[str, Any], values: dict[str, float] | None = None
) -> dict[str, float | int | str]:
    """Return a reliability score and illustrative scenario range.

    The range is a product scenario, not a statistically calibrated confidence
    interval. Reliability rewards sample size, contextual completeness, stable
    recent form, and agreement between the three methods.
    """
    method_values = values or compare_methods(stats)
    finite_values = [
        _bounded_number(value, maximum=MAX_VALUE_MILLIONS)
        for value in method_values.values()
    ]
    if not finite_values or not _has_season_data(stats):
        return {"score": 0, "label": "Low", "low": 0.0, "high": 0.0}

    minutes = _stat(stats, "minutes")
    sample_score = min(minutes / 2_700.0, 1.0)
    context_fields = (
        "contract_years",
        "injury_risk",
        "league_strength",
        "club_selling_power",
        "recent_fee",
    )
    completeness = sum(stats.get(field) not in (None, "") for field in context_fields)
    completeness_score = completeness / len(context_fields)

    average = sum(finite_values) / len(finite_values)
    spread = max(finite_values) - min(finite_values)
    agreement_score = max(0.0, 1.0 - spread / max(average, 1.0))

    form_values = [
        _bounded_number(value, maximum=10.0)
        for value in stats.get("form", [])
        if value is not None
    ]
    if len(form_values) >= 2:
        form_spread = max(form_values) - min(form_values)
        stability_score = max(0.0, 1.0 - form_spread / 2.0)
    else:
        stability_score = 0.35

    score = int(
        round(
            sample_score * 35
            + completeness_score * 25
            + agreement_score * 30
            + stability_score * 10
        )
    )
    score = min(max(score, 0), 100)
    label = "High" if score >= 80 else "Medium" if score >= 60 else "Low"
    scenario_padding = 0.08 + (100 - score) / 250.0
    half_width = max(spread / 2.0, average * scenario_padding)
    method_low = min(finite_values)
    method_high = max(finite_values)
    return {
        "score": score,
        "label": label,
        "low": _positive(max(0.0, min(method_low, average - half_width))),
        "high": _positive(max(method_high, average + half_width)),
    }
