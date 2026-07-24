"""Reproducible transfer-value regression baseline.

The bundled model is demonstrative: real production credibility requires licensed,
historical transfer-fee labels. The API statistics alone do not provide them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURES = [
    "age",
    "appearances",
    "minutes",
    "rating",
    "goals",
    "assists",
    "key_passes",
    "tackles",
    "interceptions",
    "duels_won",
    "dribbles",
    "clean_sheets",
    "saves",
    "conceded",
]
CATEGORICAL_FEATURES = ["position"]


@dataclass(frozen=True)
class ValuationResult:
    value_millions: float
    model_name: str
    caveat: str


def _demo_dataset(seed: int = 42, rows: int = 500) -> pd.DataFrame:
    """Create deterministic plausible data for a software-demo baseline only."""
    rng = np.random.default_rng(seed)
    position = rng.choice(["Goalkeeper", "Defender", "Midfielder", "Attacker"], rows)
    age = rng.integers(18, 36, rows)
    appearances = rng.integers(5, 39, rows)
    minutes = appearances * rng.integers(55, 91, rows)
    rating = np.clip(rng.normal(6.8, 0.55, rows), 5.0, 8.8)
    attack = (position == "Attacker").astype(int)
    midfield = (position == "Midfielder").astype(int)
    defender = (position == "Defender").astype(int)
    keeper = (position == "Goalkeeper").astype(int)
    goals = rng.poisson(0.18 * appearances * (1 + 1.8 * attack + 0.7 * midfield))
    assists = rng.poisson(0.12 * appearances * (1 + attack + midfield))
    key_passes = rng.poisson(0.7 * appearances * (1 + midfield))
    tackles = rng.poisson(1.2 * appearances * (1 + defender + 0.5 * midfield))
    interceptions = rng.poisson(0.7 * appearances * (1 + defender))
    duels_won = rng.poisson(2.5 * appearances)
    dribbles = rng.poisson(0.7 * appearances * (1 + attack + midfield))
    clean_sheets = rng.binomial(appearances, 0.25) * (defender + keeper)
    saves = rng.poisson(2.6 * appearances) * keeper
    conceded = rng.poisson(1.15 * appearances) * keeper
    potential = np.maximum(0, 30 - age) * 1.8
    fee = (
        1.5
        + potential
        + goals * 1.25
        + assists * 0.9
        + rating * 3.2
        + appearances * 0.25
        + clean_sheets * 0.45
        + rng.normal(0, 5, rows)
    )
    return pd.DataFrame(
        {
            "age": age,
            "appearances": appearances,
            "minutes": minutes,
            "rating": rating,
            "goals": goals,
            "assists": assists,
            "key_passes": key_passes,
            "tackles": tackles,
            "interceptions": interceptions,
            "duels_won": duels_won,
            "dribbles": dribbles,
            "clean_sheets": clean_sheets,
            "saves": saves,
            "conceded": conceded,
            "position": position,
            "market_value_millions": np.maximum(fee, 0.5),
        }
    )


def build_pipeline() -> Pipeline:
    numeric = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categories = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return Pipeline(
        [
            (
                "features",
                ColumnTransformer(
                    [
                        ("numeric", numeric, NUMERIC_FEATURES),
                        ("categories", categories, CATEGORICAL_FEATURES),
                    ]
                ),
            ),
            ("model", Ridge(alpha=8.0)),
        ]
    )


@lru_cache(maxsize=1)
def demo_model() -> Pipeline:
    data = _demo_dataset()
    return build_pipeline().fit(
        data[NUMERIC_FEATURES + CATEGORICAL_FEATURES],
        data["market_value_millions"],
    )


def evaluate_demo_model() -> dict[str, float]:
    data = _demo_dataset()
    train = data.sample(frac=0.8, random_state=42)
    test = data.drop(train.index)
    model = build_pipeline().fit(
        train[NUMERIC_FEATURES + CATEGORICAL_FEATURES],
        train["market_value_millions"],
    )
    predicted = model.predict(test[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    return {
        "mae_millions": round(float(mean_absolute_error(test["market_value_millions"], predicted)), 2),
        "r2": round(float(r2_score(test["market_value_millions"], predicted)), 3),
        "test_rows": len(test),
    }


def predict_value(player: dict) -> ValuationResult:
    row = {feature: player.get(feature, 0) for feature in NUMERIC_FEATURES}
    row["position"] = player.get("position", "Unknown")
    prediction = max(0.5, float(demo_model().predict(pd.DataFrame([row]))[0]))
    return ValuationResult(
        value_millions=round(prediction, 2),
        model_name="Ridge regression baseline",
        caveat="Trained on synthetic demonstration data; not an official market valuation.",
    )


def feature_comparison(first: dict, second: dict) -> list[dict]:
    """Return normalized evidence used by both charts and explanations."""
    metrics = ["rating", "goals", "assists", "key_passes", "tackles", "interceptions", "duels_won"]
    result = []
    for metric in metrics:
        a, b = float(first.get(metric, 0)), float(second.get(metric, 0))
        maximum = max(a, b, 1.0)
        result.append(
            {
                "metric": metric.replace("_", " ").title(),
                "first": a,
                "second": b,
                "first_normalized": round(a / maximum * 100, 1),
                "second_normalized": round(b / maximum * 100, 1),
            }
        )
    return result
