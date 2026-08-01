"""Small, deterministic fantasy-football domain helpers.

The module deliberately contains no Streamlit state or network calls.  A UI can
therefore recalculate a squad after every selection and render the returned
dictionaries directly.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from valuation import MAX_VALUE_MILLIONS, compare_methods

MIN_SQUAD_SIZE = 1
MAX_SQUAD_SIZE = 8
DEFAULT_SQUAD_SIZE = 5
DEFAULT_BUDGET_MILLIONS = 100.0
CAPTAIN_MULTIPLIER = 2
MIN_PLAYER_PRICE_MILLIONS = 4.0
MAX_PLAYER_PRICE_MILLIONS = 25.0

_STAT_LIMITS = {
    "games": 80,
    "minutes": 6_000,
    "goals": 100,
    "assists": 100,
    "clean_sheets": 60,
    "saves": 500,
    "conceded": 300,
    "yellow_cards": 30,
    "red_cards": 10,
    "rating": 10,
}


def _number(
    value: Any,
    *,
    default: float | None = 0.0,
    minimum: float = 0.0,
    maximum: float,
) -> float | None:
    """Return a finite, bounded number without trusting provider data."""
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return min(max(number, minimum), maximum)


def _first_stat(player: Mapping[str, Any], *keys: str, maximum: float) -> float:
    for key in keys:
        if key in player and player.get(key) not in (None, ""):
            value = _number(player.get(key), default=None, maximum=maximum)
            if value is not None:
                return float(value)
    return 0.0


def _role(player: Mapping[str, Any]) -> str:
    raw_position = str(player.get("position") or player.get("position_detail") or "")
    position = re.sub(r"[^a-z]+", " ", raw_position.casefold()).strip()
    tokens = set(position.split())
    if position in {"g", "gk"} or "goalkeeper" in tokens or "keeper" in tokens:
        return "Goalkeeper"
    if (
        position in {"d", "df"}
        or "defender" in tokens
        or "back" in tokens
        or "back" in position.replace(" ", "-")
    ):
        return "Defender"
    if position in {"m", "mf"} or "midfielder" in tokens or "midfield" in tokens:
        return "Midfielder"
    if position in {"f", "fw"} or tokens.intersection(
        {"attacker", "forward", "striker", "winger"}
    ):
        return "Attacker"
    return "Unknown"


def player_identity(player: Mapping[str, Any]) -> str | None:
    """Return a stable squad identity from common offline and API fields."""
    if not isinstance(player, Mapping):
        return None
    for key in ("player_id", "api_id", "id"):
        value = player.get(key)
        if (
            isinstance(value, (str, int))
            and not isinstance(value, bool)
            and str(value).strip()
        ):
            return str(value).strip()

    name = " ".join(str(player.get("name") or "").split()).casefold()
    if not name:
        return None
    team = " ".join(str(player.get("team") or "").split()).casefold()
    return f"name:{name}|team:{team}"


def score_player(player: Mapping[str, Any]) -> dict[str, Any]:
    """Score aggregate season statistics with a transparent FPL-style model.

    Provider data only contains season totals, not minutes from each individual
    fixture.  The minute bonus is consequently estimated as one extra point for
    each 60-minute equivalent, capped by the number of appearances.
    """
    if not isinstance(player, Mapping):
        player = {}

    role = _role(player)
    games = int(
        _first_stat(
            player,
            "games",
            "appearances",
            "appearences",
            maximum=_STAT_LIMITS["games"],
        )
    )
    minutes = int(_first_stat(player, "minutes", maximum=_STAT_LIMITS["minutes"]))
    if games == 0 and minutes > 0:
        games = min(_STAT_LIMITS["games"], math.ceil(minutes / 90))

    sixty_minute_equivalents = min(games, minutes // 60)
    appearances = games + sixty_minute_equivalents

    goals = int(_first_stat(player, "goals", maximum=_STAT_LIMITS["goals"]))
    assists = int(_first_stat(player, "assists", maximum=_STAT_LIMITS["assists"]))
    clean_sheets = int(
        _first_stat(
            player,
            "clean_sheets",
            "cleansheets",
            maximum=_STAT_LIMITS["clean_sheets"],
        )
    )
    saves = int(_first_stat(player, "saves", maximum=_STAT_LIMITS["saves"]))
    conceded = int(_first_stat(player, "conceded", maximum=_STAT_LIMITS["conceded"]))
    yellow_cards = int(
        _first_stat(
            player,
            "yellow_cards",
            "yellow",
            "cards_yellow",
            maximum=_STAT_LIMITS["yellow_cards"],
        )
    )
    red_cards = int(
        _first_stat(
            player,
            "red_cards",
            "red",
            "cards_red",
            maximum=_STAT_LIMITS["red_cards"],
        )
    )
    rating = _first_stat(player, "rating", maximum=_STAT_LIMITS["rating"])

    goal_weight = {
        "Goalkeeper": 6,
        "Defender": 6,
        "Midfielder": 5,
        "Attacker": 4,
        "Unknown": 4,
    }[role]
    clean_sheet_weight = {
        "Goalkeeper": 4,
        "Defender": 4,
        "Midfielder": 1,
        "Attacker": 0,
        "Unknown": 0,
    }[role]
    rating_bonus = (
        12 if rating >= 8.0 else 8 if rating >= 7.5 else 4 if rating >= 7.0 else 0
    )

    breakdown = {
        "appearances": appearances,
        "goals": goals * goal_weight,
        "assists": assists * 3,
        "clean_sheets": clean_sheets * clean_sheet_weight,
        "saves": saves // 3 if role == "Goalkeeper" else 0,
        "conceded": -(conceded // 2) if role in {"Goalkeeper", "Defender"} else 0,
        "yellow_cards": -yellow_cards,
        "red_cards": -(red_cards * 3),
        "rating_bonus": rating_bonus,
    }
    return {
        "player_id": player_identity(player),
        "position": role,
        "base_points": sum(breakdown.values()),
        "breakdown": breakdown,
        "inputs": {
            "games": games,
            "minutes": minutes,
            "rating": round(rating, 2),
        },
    }


def _blended_valuation(
    player: Mapping[str, Any], provided_value: Any = None
) -> tuple[float, str]:
    direct = _number(
        provided_value,
        default=None,
        maximum=MAX_VALUE_MILLIONS,
    )
    if direct is not None:
        return direct, "provided"

    for field in ("blended_value", "blended_valuation", "estimated_value"):
        if field in player:
            direct = _number(
                player.get(field), default=None, maximum=MAX_VALUE_MILLIONS
            )
            if direct is not None:
                return direct, "provided"

    try:
        methods = compare_methods(dict(player))
    except (TypeError, ValueError, OverflowError):
        methods = {}
    finite_values = [
        value
        for raw_value in methods.values()
        if (
            value := _number(
                raw_value,
                default=None,
                maximum=MAX_VALUE_MILLIONS,
            )
        )
        is not None
    ]
    if not finite_values:
        return 0.0, "fallback"
    return round(sum(finite_values) / len(finite_values), 2), "valuation_methods"


def calculate_player_price(
    player: Mapping[str, Any], *, blended_value: Any = None
) -> dict[str, float | str]:
    """Convert a blended market estimate into a budget-friendly fantasy price.

    The square-root scale compresses the existing 0–250 million valuation range
    into 4–25 million, keeping both five- and eight-player squads practical.
    """
    if not isinstance(player, Mapping):
        player = {}
    valuation, source = _blended_valuation(player, blended_value)
    price = MIN_PLAYER_PRICE_MILLIONS + math.sqrt(valuation) * 1.25
    price = min(max(price, MIN_PLAYER_PRICE_MILLIONS), MAX_PLAYER_PRICE_MILLIONS)
    return {
        "price": round(price, 1),
        "blended_value": round(valuation, 2),
        "source": source,
    }


def _provided_value(
    blended_values: Mapping[str, Any] | None,
    player: Mapping[str, Any],
    identity: str | None,
) -> Any:
    if not isinstance(blended_values, Mapping):
        return None
    candidates = (
        identity,
        player.get("player_id"),
        player.get("api_id"),
        player.get("id"),
        player.get("name"),
    )
    for candidate in candidates:
        if isinstance(candidate, (str, int)) and candidate in blended_values:
            return blended_values[candidate]
        text_candidate = str(candidate) if candidate is not None else None
        if text_candidate is not None and text_candidate in blended_values:
            return blended_values[text_candidate]
    return None


def _prepare_players(
    players: Sequence[Mapping[str, Any]],
    blended_values: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for index, raw_player in enumerate(players):
        player = raw_player if isinstance(raw_player, Mapping) else {}
        identity = player_identity(player)
        price = calculate_player_price(
            player,
            blended_value=_provided_value(blended_values, player, identity),
        )
        prepared.append(
            {
                "index": index,
                "player": player,
                "player_id": identity,
                "name": str(player.get("name") or f"Player {index + 1}"),
                **price,
            }
        )
    return prepared


def _settings_errors(
    squad_size: Any, budget: Any
) -> tuple[int | None, float | None, list[str]]:
    errors: list[str] = []
    size_number = _number(
        squad_size,
        default=None,
        minimum=MIN_SQUAD_SIZE,
        maximum=MAX_SQUAD_SIZE,
    )
    if (
        size_number is None
        or isinstance(squad_size, bool)
        or not size_number.is_integer()
        or float(squad_size) != size_number
    ):
        normalised_size = None
    else:
        normalised_size = int(size_number)
    if normalised_size is None:
        errors.append(
            f"Squad size must be between {MIN_SQUAD_SIZE} and {MAX_SQUAD_SIZE}."
        )

    normalised_budget = _number(
        budget,
        default=None,
        minimum=-1_000_000.0,
        maximum=1_000_000.0,
    )
    if normalised_budget is None or normalised_budget <= 0:
        normalised_budget = None
        errors.append("Budget must be a positive number.")
    return normalised_size, normalised_budget, errors


def validate_squad(
    players: Sequence[Mapping[str, Any]],
    captain_id: str | int | None,
    *,
    squad_size: int = DEFAULT_SQUAD_SIZE,
    budget: float = DEFAULT_BUDGET_MILLIONS,
    blended_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate squad composition, budget, identity, and captain selection."""
    if isinstance(players, (str, bytes)) or not isinstance(players, Sequence):
        players = []
        input_error = "Players must be supplied as a sequence."
    else:
        input_error = None

    prepared = _prepare_players(players, blended_values)
    normalised_size, normalised_budget, errors = _settings_errors(squad_size, budget)
    if input_error:
        errors.insert(0, input_error)
    if normalised_size is not None and len(prepared) != normalised_size:
        errors.append(
            f"Choose exactly {normalised_size} player"
            f"{'s' if normalised_size != 1 else ''}; currently {len(prepared)}."
        )

    identities = [item["player_id"] for item in prepared]
    if any(identity is None for identity in identities):
        errors.append("Every player needs a stable ID or name.")
    valid_identities = [identity for identity in identities if identity is not None]
    if len(set(valid_identities)) != len(valid_identities):
        errors.append("A player can only appear once in a squad.")

    normalised_captain = (
        str(captain_id).strip()
        if captain_id is not None and not isinstance(captain_id, bool)
        else ""
    )
    if not normalised_captain:
        errors.append("Choose one captain.")
    elif normalised_captain not in valid_identities:
        errors.append("The captain must be one of the selected players.")

    total_value = round(sum(item["price"] for item in prepared), 1)
    budget_remaining = (
        round(normalised_budget - total_value, 1)
        if normalised_budget is not None
        else None
    )
    if budget_remaining is not None and budget_remaining < 0:
        errors.append(f"Squad is €{abs(budget_remaining):.1f}M over the budget.")

    return {
        "is_valid": not errors,
        "errors": errors,
        "player_count": len(prepared),
        "required_player_count": normalised_size,
        "captain_id": normalised_captain or None,
        "total_value": total_value,
        "budget": (
            round(normalised_budget, 1) if normalised_budget is not None else None
        ),
        "budget_remaining": budget_remaining,
        "prices": {
            item["player_id"]: item["price"]
            for item in prepared
            if item["player_id"] is not None
        },
    }


def calculate_squad(
    players: Sequence[Mapping[str, Any]],
    captain_id: str | int | None,
    *,
    squad_size: int = DEFAULT_SQUAD_SIZE,
    budget: float = DEFAULT_BUDGET_MILLIONS,
    blended_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a complete validation, price, and points summary for a squad."""
    safe_players = (
        players
        if isinstance(players, Sequence) and not isinstance(players, (str, bytes))
        else []
    )
    prepared = _prepare_players(safe_players, blended_values)
    validation = validate_squad(
        players,
        captain_id,
        squad_size=squad_size,
        budget=budget,
        blended_values=blended_values,
    )
    captain = validation["captain_id"]
    rows: list[dict[str, Any]] = []
    for item in prepared:
        scoring = score_player(item["player"])
        is_captain = item["player_id"] is not None and item["player_id"] == captain
        multiplier = CAPTAIN_MULTIPLIER if is_captain else 1
        rows.append(
            {
                "player_id": item["player_id"],
                "name": item["name"],
                "position": scoring["position"],
                "season": item["player"].get("season"),
                "price": item["price"],
                "blended_value": item["blended_value"],
                "price_source": item["source"],
                "is_captain": is_captain,
                "multiplier": multiplier,
                "base_points": scoring["base_points"],
                "points": scoring["base_points"] * multiplier,
                "breakdown": scoring["breakdown"],
                "inputs": scoring["inputs"],
            }
        )

    return {
        **validation,
        "total_points": sum(item["points"] for item in rows),
        "base_points": sum(item["base_points"] for item in rows),
        "captain_bonus": sum(item["points"] - item["base_points"] for item in rows),
        "players": rows,
        "rules": {
            "minimum_squad_size": MIN_SQUAD_SIZE,
            "maximum_squad_size": MAX_SQUAD_SIZE,
            "default_squad_size": DEFAULT_SQUAD_SIZE,
            "captain_multiplier": CAPTAIN_MULTIPLIER,
        },
    }
