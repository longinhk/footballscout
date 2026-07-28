"""API-Football client and response normalisation."""

from __future__ import annotations

import math
import os
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

API_URL = "https://api-football-v1.p.rapidapi.com/v3/players"


class FootballAPIError(RuntimeError):
    """A user-facing API error."""


def get_api_key() -> str | None:
    """Read the key from Streamlit secrets first, then the environment."""
    secret_locations = (
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    )
    if any(path.is_file() for path in secret_locations):
        try:
            import streamlit as st

            secret_key = st.secrets.get("RAPIDAPI_KEY")
            if secret_key and str(secret_key).strip():
                return str(secret_key).strip()
        except (FileNotFoundError, KeyError):
            pass

    environment_key = os.getenv("RAPIDAPI_KEY")
    return (
        environment_key.strip() if environment_key and environment_key.strip() else None
    )


def _finite_number(value: Any) -> float | None:
    """Return a finite number, or ``None`` for absent/malformed API values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int:
    """Normalise cumulative statistics to non-negative integer counts."""
    number = _finite_number(value)
    return max(0, int(number)) if number is not None else 0


def _text(value: Any, default: str = "Unknown") -> str:
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value or default


def _section(row: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = row.get(name)
    return section if isinstance(section, Mapping) else {}


def _display_scope(names: list[str], noun: str) -> str:
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    return f"{len(names)} {noun}"


def parse_player_response(
    data: dict[str, Any], season: str | int | None = None
) -> dict[str, Any]:
    """Convert and aggregate an API-Football player response.

    API-Football returns one statistics row per team and competition.  The app
    presents a season-wide view, so cumulative fields are summed and ratings
    are weighted by minutes (then appearances when minutes are unavailable).
    """
    if not isinstance(data, Mapping) or "response" not in data:
        raise FootballAPIError("The API returned an unexpected response format.")

    responses = data.get("response")
    if not isinstance(responses, list):
        raise FootballAPIError("The API returned an unexpected response format.")
    if not responses:
        api_error = data.get("errors")
        detail = f" ({api_error})" if api_error else ""
        raise FootballAPIError(f"No player data was returned{detail}.")

    response = responses[0]
    if not isinstance(response, Mapping):
        raise FootballAPIError("The API returned an unexpected response format.")
    player_info = response.get("player")
    statistics = response.get("statistics")
    if not isinstance(player_info, Mapping) or not isinstance(statistics, list):
        raise FootballAPIError("The API returned an unexpected response format.")

    totals = defaultdict(int)
    rating_total = 0.0
    rating_weight = 0.0
    position_weights: dict[str, float] = defaultdict(float)
    teams: list[str] = []
    competitions: list[str] = []
    competition_ids: set[tuple[str, str]] = set()
    clean_sheets_total = 0
    clean_sheets_available = False
    valid_rows = 0

    for row_index, row in enumerate(statistics):
        if not isinstance(row, Mapping):
            continue
        games = _section(row, "games")
        goals = _section(row, "goals")
        tackles = _section(row, "tackles")
        if not games and not goals and not tackles:
            continue
        valid_rows += 1

        appearances = _count(games.get("appearences"))
        minutes = _count(games.get("minutes"))
        totals["games"] += appearances
        totals["minutes"] += minutes
        totals["goals"] += _count(goals.get("total"))
        totals["assists"] += _count(goals.get("assists"))
        totals["conceded"] += _count(goals.get("conceded"))
        totals["saves"] += _count(goals.get("saves"))
        totals["tackles"] += _count(tackles.get("total"))
        totals["interceptions"] += _count(tackles.get("interceptions"))

        rating = _finite_number(games.get("rating"))
        if rating is not None:
            weight = float(minutes or appearances or 1)
            rating_total += min(max(rating, 0.0), 10.0) * weight
            rating_weight += weight

        position = _text(games.get("position"))
        if position != "Unknown":
            position_weights[position] += float(minutes or appearances or 1)

        team = _section(row, "team")
        team_name = _text(team.get("name"))
        if team_name != "Unknown" and team_name not in teams:
            teams.append(team_name)

        league = _section(row, "league")
        league_name = _text(league.get("name"))
        if league_name != "Unknown" and league_name not in competitions:
            competitions.append(league_name)
        league_id = league.get("id")
        if league_id is not None:
            competition_ids.add(("id", str(league_id)))
        elif league_name != "Unknown":
            competition_ids.add(("name", league_name.casefold()))
        else:
            competition_ids.add(("row", str(row_index)))

        for field in ("cleansheets", "clean_sheets"):
            if field not in games:
                continue
            clean_sheets = _finite_number(games.get(field))
            if clean_sheets is not None:
                clean_sheets_available = True
                clean_sheets_total += max(0, int(clean_sheets))
            break

    if valid_rows == 0:
        raise FootballAPIError("The API returned no usable player statistics.")

    parameters = data.get("parameters")
    response_season = (
        parameters.get("season") if isinstance(parameters, Mapping) else None
    )
    season_label = _text(season if season is not None else response_season)
    position = (
        max(position_weights, key=position_weights.get)
        if position_weights
        else "Unknown"
    )
    photo = player_info.get("photo")

    age = _finite_number(player_info.get("age"))
    scope = (
        competitions[0]
        if valid_rows == 1 and len(competitions) == 1
        else "All teams and competitions"
    )

    return {
        "name": _text(player_info.get("name")),
        "photo": photo.strip() if isinstance(photo, str) and photo.strip() else None,
        "age": max(0, int(age)) if age is not None else None,
        "team": _display_scope(teams, "teams"),
        "league": _display_scope(competitions, "competitions"),
        "teams": teams,
        "competitions": competitions,
        "position": position,
        "games": totals["games"],
        "minutes": totals["minutes"],
        "rating": round(rating_total / rating_weight, 2) if rating_weight else None,
        "goals": totals["goals"],
        "assists": totals["assists"],
        "conceded": totals["conceded"],
        "saves": totals["saves"],
        "tackles": totals["tackles"],
        "interceptions": totals["interceptions"],
        "clean_sheets": clean_sheets_total if clean_sheets_available else None,
        "scope": scope,
        "season": season_label,
        "competition_count": max(1, len(competition_ids)),
    }


def fetch_player_stats(
    player_id: int, season: str = "2024", api_key: str | None = None
) -> dict[str, Any]:
    """Fetch and normalise one player's season statistics."""
    try:
        player_id_text = str(player_id).strip()
        if not player_id_text.isdigit() or int(player_id_text) <= 0:
            raise ValueError
        normalised_player_id = int(player_id_text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FootballAPIError("Player ID must be a positive integer.") from exc

    season_text = str(season).strip()
    if len(season_text) != 4 or not season_text.isdigit():
        raise FootballAPIError("Season must be a four-digit start year.")

    key_source = api_key if api_key is not None else get_api_key()
    key = str(key_source).strip() if key_source is not None else ""
    if not key:
        raise FootballAPIError(
            "API key is missing. Enter a non-blank API-Football key or "
            "configure RAPIDAPI_KEY."
        )

    try:
        response = requests.get(
            API_URL,
            headers={
                "X-RapidAPI-Key": key,
                "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
            },
            params={"id": normalised_player_id, "season": season_text},
            timeout=15,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise FootballAPIError("The football API timed out. Please retry.") from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if status == 401:
            message = (
                "The football API rejected the API key (HTTP 401). "
                "Check that the key is valid."
            )
        elif status == 403:
            message = (
                "The football API denied access (HTTP 403). "
                "Check your subscription and API permissions."
            )
        elif status == 429:
            message = (
                "The football API rate limit was reached (HTTP 429). "
                "Wait before retrying or check your plan quota."
            )
        elif isinstance(status, int) and status >= 500:
            message = (
                f"The football API is temporarily unavailable (HTTP {status}). "
                "Please retry shortly."
            )
        else:
            message = (
                f"The football API rejected the request (HTTP {status}). "
                "Check the player ID and season."
            )
        raise FootballAPIError(message) from exc
    except requests.RequestException as exc:
        raise FootballAPIError(f"Could not reach the football API: {exc}") from exc

    try:
        return parse_player_response(response.json(), season=season_text)
    except (requests.JSONDecodeError, ValueError) as exc:
        raise FootballAPIError("The football API returned invalid JSON.") from exc
