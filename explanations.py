"""Grounded comparison explanations with an optional OpenAI enhancement."""

from __future__ import annotations

import json
import os

from valuation import ValuationResult, feature_comparison


def deterministic_explanation(
    first: dict,
    second: dict,
    first_value: ValuationResult,
    second_value: ValuationResult,
) -> str:
    winner, loser = (
        (first, second)
        if first_value.value_millions >= second_value.value_millions
        else (second, first)
    )
    winner_value = max(first_value.value_millions, second_value.value_millions)
    loser_value = min(first_value.value_millions, second_value.value_millions)
    evidence = []
    for item in feature_comparison(winner, loser):
        if item["first"] > item["second"]:
            evidence.append(f"{item['metric'].lower()} ({item['first']:g} vs {item['second']:g})")
    reasons = ", ".join(evidence[:3]) or "the combined model inputs"
    return (
        f"{winner['name']} receives the higher demonstration estimate "
        f"(€{winner_value:.2f}M vs €{loser_value:.2f}M). The strongest visible advantages are "
        f"{reasons}. Age, position and playing time also affect the regression. "
        "This is model interpretation, not evidence of an actual transfer price."
    )


def llm_explanation(
    first: dict,
    second: dict,
    first_value: ValuationResult,
    second_value: ValuationResult,
    api_key: str | None = None,
) -> str:
    """Use Responses API only when configured; never invent unavailable facts."""
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return deterministic_explanation(first, second, first_value, second_value)
    try:
        from openai import OpenAI

        evidence = {
            "players": [first, second],
            "estimates_millions": [first_value.value_millions, second_value.value_millions],
            "model": first_value.model_name,
            "limitation": first_value.caveat,
        }
        response = OpenAI(api_key=key).responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            reasoning={"effort": "low"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "Explain a football valuation comparison in 3 concise sentences. "
                        "Use only supplied evidence, mention uncertainty, and never call the "
                        "estimate an official market value."
                    ),
                },
                {"role": "user", "content": json.dumps(evidence, default=str)},
            ],
        )
        return response.output_text.strip()
    except Exception:
        return deterministic_explanation(first, second, first_value, second_value)
