"""Centralized, testable state transitions for the Streamlit application."""

from __future__ import annotations

import time
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import Any

MAX_REAL_SEARCHES_PER_SESSION = 8
REAL_SEARCH_COOLDOWN_SECONDS = 2.0


def initialize_session_state(
    state: MutableMapping[str, Any],
    *,
    default_pair: tuple[str, str],
    age_bounds: tuple[int, int],
    default_squad_size: int = 5,
) -> None:
    """Install application defaults without replacing restored session values."""
    defaults: dict[str, Any] = {
        "watchlist_ids": [],
        "saved_matchups": [],
        "last_valid_ids": default_pair,
        "offline_player_a": default_pair[0],
        "offline_player_b": default_pair[1],
        "offline_search": "",
        "filter_positions": [],
        "filter_leagues": [],
        "filter_age": age_bounds,
        "filter_minutes": 0,
        "real_profile_cache": {},
        "real_favorites": {},
        "real_search_count": 0,
        "fantasy_league": [],
        "fantasy_selected_ids": [],
        "workspace_mode": "Compare players",
        "fantasy_pool_mode": "Sample catalog",
        "fantasy_squad_size": default_squad_size,
    }
    for key, value in defaults.items():
        if key not in state:
            state[key] = deepcopy(value)


def claim_real_search(
    state: MutableMapping[str, Any],
    side: str,
    *,
    now: float | None = None,
    cooldown_seconds: float = REAL_SEARCH_COOLDOWN_SECONDS,
    maximum_searches: int = MAX_REAL_SEARCHES_PER_SESSION,
) -> str | None:
    """Reserve one profile search or return a friendly session-limit message."""
    current_time = time.time() if now is None else float(now)
    count = max(0, int(state.get("real_search_count", 0) or 0))
    if count >= maximum_searches:
        return (
            "This browser session has reached its real-player search limit. "
            "Use the Sample catalog or start a new session later."
        )

    bucket = str(side).strip().casefold() or "player"
    last_key = f"real_search_last_at_{bucket}"
    try:
        last_search = float(state.get(last_key, 0.0) or 0.0)
    except (TypeError, ValueError, OverflowError):
        last_search = 0.0
    wait = max(0.0, cooldown_seconds - (current_time - last_search))
    if wait > 0:
        return f"Please wait {max(1, round(wait))} second before searching again."

    state["real_search_count"] = count + 1
    state[last_key] = current_time
    return None


def preserve_selected_pool(
    unfiltered_pool: Mapping[str, Mapping[str, Any]],
    filtered_players: list[Mapping[str, Any]],
    selected_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    """Keep valid selected players visible even when filters no longer match."""
    normalized_pool = {
        str(player_id): dict(player) for player_id, player in unfiltered_pool.items()
    }
    visible = {
        str(player.get("player_id")): dict(player)
        for player in filtered_players
        if player.get("player_id") is not None
    }
    retained = [player_id for player_id in selected_ids if player_id in normalized_pool]
    hidden_selected = 0
    for player_id in retained:
        if player_id not in visible:
            visible[player_id] = normalized_pool[player_id]
            hidden_selected += 1
    return visible, retained, hidden_selected


def seed_fantasy_from_comparison(
    state: MutableMapping[str, Any],
    players: list[Mapping[str, Any]],
    *,
    maximum_squad_size: int = 8,
) -> None:
    """Save a real matchup and open Fantasy with those players preselected."""
    favorites = {
        str(player_id): dict(player)
        for player_id, player in dict(state.get("real_favorites", {})).items()
    }
    selected_ids: list[str] = []
    seasons: set[str] = set()
    for player in players:
        player_id = str(player.get("player_id") or "").strip()
        if not player_id.startswith("api-"):
            continue
        snapshot = dict(player)
        favorites[player_id] = snapshot
        selected_ids.append(player_id)
        if player.get("season") is not None:
            seasons.add(str(player.get("season")))

    state["real_favorites"] = favorites
    state["workspace_mode"] = "Fantasy challenge"
    state["fantasy_pool_mode"] = "Real favourites"
    state["fantasy_selected_ids"] = selected_ids[:maximum_squad_size]
    if len(seasons) == 1:
        state["fantasy_favorite_season"] = next(iter(seasons))
    if selected_ids:
        state["fantasy_squad_size"] = min(len(selected_ids), maximum_squad_size)
        state["fantasy_captain"] = selected_ids[0]
