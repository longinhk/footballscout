"""Offline scouting profiles, watchlists, and portable workspace helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

from valuation import per_90

PROFILE_DIMENSIONS = (
    "Availability",
    "Form",
    "Primary output",
    "Support output",
    "Defensive work",
    "Progression",
)
WORKSPACE_SCHEMA_VERSION = 1


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _role(player: Mapping[str, Any]) -> str:
    value = str(player.get("position") or "").lower()
    for role in ("goalkeeper", "defender", "midfielder", "attacker"):
        if role in value:
            return role
    return "unknown"


def _clean_sheet_rate(player: Mapping[str, Any]) -> float:
    games = _number(player.get("games"))
    return _number(player.get("clean_sheets")) / games if games > 0 else 0.0


def _dimension_values(player: Mapping[str, Any]) -> dict[str, float]:
    minutes = _number(player.get("minutes"))
    role = _role(player)
    goals_rate = per_90(player.get("goals"), minutes, maximum=4.0)
    assists_rate = per_90(player.get("assists"), minutes, maximum=4.0)
    tackles_rate = per_90(player.get("tackles"), minutes, maximum=15.0)
    interceptions_rate = per_90(player.get("interceptions"), minutes, maximum=12.0)
    saves_rate = per_90(player.get("saves"), minutes, maximum=15.0)
    conceded_rate = per_90(player.get("conceded"), minutes, maximum=6.0)
    key_pass_rate = per_90(player.get("key_passes"), minutes, maximum=10.0)
    shots_rate = per_90(player.get("shots"), minutes, maximum=10.0)
    progression_rate = per_90(player.get("progressive_actions"), minutes, maximum=20.0)
    pass_accuracy = _number(player.get("pass_accuracy"))
    clean_sheet_rate = _clean_sheet_rate(player)

    if role == "goalkeeper":
        primary = saves_rate + clean_sheet_rate * 4.0 + max(0.0, 2.5 - conceded_rate)
        support = pass_accuracy / 20.0 + progression_rate / 4.0
        defensive = clean_sheet_rate * 8.0 + max(0.0, 3.0 - conceded_rate)
    elif role == "defender":
        primary = tackles_rate + interceptions_rate + clean_sheet_rate * 3.0
        support = assists_rate * 3.0 + progression_rate / 3.0
        defensive = tackles_rate + interceptions_rate + clean_sheet_rate * 4.0
    elif role == "midfielder":
        primary = assists_rate * 4.0 + key_pass_rate + progression_rate / 4.0
        support = goals_rate * 3.0 + tackles_rate / 3.0 + interceptions_rate / 3.0
        defensive = tackles_rate + interceptions_rate
    elif role == "attacker":
        primary = goals_rate * 5.0 + shots_rate / 2.0
        support = assists_rate * 4.0 + key_pass_rate
        defensive = tackles_rate + interceptions_rate
    else:
        primary = goals_rate + assists_rate + saves_rate
        support = key_pass_rate + progression_rate
        defensive = tackles_rate + interceptions_rate

    return {
        "Availability": min(minutes / 2_700.0, 1.3),
        "Form": _number(player.get("rating")),
        "Primary output": primary,
        "Support output": support,
        "Defensive work": defensive,
        "Progression": progression_rate + pass_accuracy / 15.0,
    }


def _percentile(value: float, values: Sequence[float]) -> int:
    if not values:
        return 50
    lower = sum(candidate < value for candidate in values)
    equal = sum(abs(candidate - value) < 1e-9 for candidate in values)
    rank = (lower + equal * 0.5) / len(values)
    return int(round(rank * 100))


def profile_percentiles(
    player: Mapping[str, Any], roster: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    """Return role-cohort percentiles for six positive scouting dimensions."""
    role = _role(player)
    cohort = [candidate for candidate in roster if _role(candidate) == role]
    if not cohort:
        cohort = list(roster)
    player_values = _dimension_values(player)
    cohort_values = [_dimension_values(candidate) for candidate in cohort]
    return {
        dimension: _percentile(
            player_values[dimension],
            [values[dimension] for values in cohort_values],
        )
        for dimension in PROFILE_DIMENSIONS
    }


def form_summary(player: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize the checked-in recent-form periods for presentation."""
    values = [
        _number(value)
        for value in player.get("form", [])
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    if not values:
        return {"values": [], "average": None, "delta": 0.0, "direction": "No data"}
    delta = values[-1] - values[0]
    direction = "Rising" if delta > 0.12 else "Cooling" if delta < -0.12 else "Stable"
    return {
        "values": values,
        "average": round(sum(values) / len(values), 2),
        "delta": round(delta, 2),
        "direction": direction,
    }


def add_to_watchlist(
    current: Iterable[str], player_id: str, valid_ids: Collection[str]
) -> list[str]:
    """Add one valid player while preserving order and preventing duplicates."""
    result = [value for value in current if value in valid_ids]
    if player_id not in valid_ids:
        raise ValueError("Unknown offline player ID.")
    if player_id not in result:
        result.append(player_id)
    return result


def remove_from_watchlist(current: Iterable[str], player_id: str) -> list[str]:
    return [value for value in current if value != player_id]


def save_matchup(
    current: Iterable[Sequence[str]], first_id: str, second_id: str
) -> list[list[str]]:
    """Save a distinct ordered matchup once."""
    if first_id == second_id:
        raise ValueError("A saved matchup requires two different players.")
    result = [list(item[:2]) for item in current if len(item) >= 2]
    candidate = [first_id, second_id]
    if candidate not in result:
        result.append(candidate)
    return result


def workspace_bytes(
    watchlist_ids: Iterable[str], saved_matchups: Iterable[Sequence[str]]
) -> bytes:
    payload = {
        "schema_version": WORKSPACE_SCHEMA_VERSION,
        "watchlist_ids": list(dict.fromkeys(watchlist_ids)),
        "saved_matchups": [list(item[:2]) for item in saved_matchups if len(item) >= 2],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def parse_workspace(
    payload: bytes | str, valid_ids: Collection[str]
) -> tuple[list[str], list[list[str]]]:
    """Validate a portable offline workspace without accepting unknown players."""
    try:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("The workspace file is not valid JSON.") from exc
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != WORKSPACE_SCHEMA_VERSION
    ):
        raise ValueError("Unsupported workspace format.")

    raw_watchlist = data.get("watchlist_ids", [])
    raw_matchups = data.get("saved_matchups", [])
    if not isinstance(raw_watchlist, list) or not isinstance(raw_matchups, list):
        raise ValueError("The workspace lists are malformed.")

    watchlist: list[str] = []
    for player_id in raw_watchlist:
        if not isinstance(player_id, str) or player_id not in valid_ids:
            raise ValueError("The workspace contains an unknown player.")
        if player_id not in watchlist:
            watchlist.append(player_id)

    matchups: list[list[str]] = []
    for matchup in raw_matchups:
        if (
            not isinstance(matchup, list)
            or len(matchup) != 2
            or not all(isinstance(player_id, str) for player_id in matchup)
            or any(player_id not in valid_ids for player_id in matchup)
            or matchup[0] == matchup[1]
        ):
            raise ValueError("The workspace contains an invalid matchup.")
        if matchup not in matchups:
            matchups.append(matchup)
    return watchlist, matchups
