"""Pure helpers for real-player discovery, sharing, and session libraries."""

from __future__ import annotations

import math
import json
from collections.abc import Iterable, Mapping
from typing import Any


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def filter_profiles(
    profiles: Iterable[Mapping[str, Any]],
    *,
    positions: Iterable[str] = (),
    nationality: str = "",
    age_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Filter already-fetched profiles without spending more API requests."""
    wanted_positions = {
        str(position).strip().casefold()
        for position in positions
        if str(position).strip()
    }
    nationality_query = " ".join(str(nationality or "").split()).casefold()
    minimum_age, maximum_age = age_range or (0, 200)

    matches: list[dict[str, Any]] = []
    for raw_profile in profiles:
        profile = dict(raw_profile)
        position = str(profile.get("position") or "").strip().casefold()
        country = str(profile.get("nationality") or "").strip().casefold()
        age = _integer(profile.get("age"))
        if wanted_positions and position not in wanted_positions:
            continue
        if nationality_query and nationality_query not in country:
            continue
        if age_range is not None and (
            age is None or not minimum_age <= age <= maximum_age
        ):
            continue
        matches.append(profile)
    return matches


def filter_player_pool(
    players: Iterable[Mapping[str, Any]],
    *,
    positions: Iterable[str] = (),
    nationality: str = "",
    club: str = "",
    competition: str = "",
    age_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Filter loaded season rows by player, club, and competition context."""
    profile_matches = filter_profiles(
        players,
        positions=positions,
        nationality=nationality,
        age_range=age_range,
    )
    club_query = " ".join(str(club or "").split()).casefold()
    competition_query = " ".join(str(competition or "").split()).casefold()
    matches = []
    for player in profile_matches:
        teams = player.get("teams")
        if not isinstance(teams, list):
            teams = [player.get("team")]
        competitions = player.get("competitions")
        if not isinstance(competitions, list):
            competitions = [player.get("league")]
        team_text = " ".join(str(value or "") for value in teams).casefold()
        competition_text = " ".join(
            str(value or "") for value in competitions
        ).casefold()
        if club_query and club_query not in team_text:
            continue
        if competition_query and competition_query not in competition_text:
            continue
        matches.append(player)
    return matches


def comparison_query(player_ids: Iterable[Any], season: Any) -> dict[str, str]:
    """Build a compact, validated query string payload for a matchup."""
    ids = [_integer(player_id) for player_id in player_ids]
    season_value = _integer(season)
    if (
        len(ids) != 2
        or any(player_id is None or player_id <= 0 for player_id in ids)
        or ids[0] == ids[1]
    ):
        raise ValueError("A shared comparison needs two different player IDs.")
    if season_value is None or not 1900 <= season_value <= 2200:
        raise ValueError("A shared comparison needs a valid four-digit season.")
    return {"a": str(ids[0]), "b": str(ids[1]), "season": str(season_value)}


def parse_comparison_query(params: Mapping[str, Any]) -> tuple[int, int, str] | None:
    """Parse public comparison parameters, returning ``None`` when incomplete."""
    if not all(key in params for key in ("a", "b", "season")):
        return None
    try:
        payload = comparison_query(
            (params.get("a"), params.get("b")), params.get("season")
        )
    except ValueError:
        return None
    return int(payload["a"]), int(payload["b"]), payload["season"]


def real_result_session_updates(
    players: list[dict[str, Any]],
    season: Any,
    first_api_id: int,
    second_api_id: int,
    *,
    sync_selectors: bool = False,
) -> dict[str, Any]:
    """Build safe session updates for manual comparisons or shared links."""
    updates: dict[str, Any] = {
        "real_season": str(season),
        "real_result": {"players": players, "season": str(season)},
        "shared_comparison_error": "",
    }
    if sync_selectors:
        updates.update(
            {
                "real_results_a": [first_api_id],
                "real_results_b": [second_api_id],
                "real_selected_a": first_api_id,
                "real_selected_b": second_api_id,
            }
        )
    return updates


def save_real_favorite(
    favorites: Mapping[str, Mapping[str, Any]], player: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return an updated, insertion-ordered real-player favourites mapping."""
    player_id = str(player.get("player_id") or "").strip()
    if (
        not player_id.startswith("api-")
        or _integer(player_id.removeprefix("api-")) is None
    ):
        raise ValueError("Only normalized API-Football players can be saved.")
    updated = {str(key): dict(value) for key, value in favorites.items()}
    updated[player_id] = dict(player)
    return updated


def remove_real_favorite(
    favorites: Mapping[str, Mapping[str, Any]], player_id: str
) -> dict[str, dict[str, Any]]:
    """Remove one real-player favourite without mutating session state in place."""
    return {
        str(key): dict(value)
        for key, value in favorites.items()
        if str(key) != str(player_id)
    }


def toggle_real_favorite_snapshot(
    favorites: Mapping[str, Mapping[str, Any]], player: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Toggle one season snapshot, updating it when the saved season changed."""
    player_id = str(player.get("player_id") or "").strip()
    saved = favorites.get(player_id)
    if saved is not None and str(saved.get("season") or "") == str(
        player.get("season") or ""
    ):
        return remove_real_favorite(favorites, player_id)
    return save_real_favorite(favorites, player)


def real_favorites_bytes(
    favorites: Mapping[str, Mapping[str, Any]],
) -> bytes:
    """Serialize a portable real-player library without credentials or cache data."""
    players = []
    for favorite in favorites.values():
        player = dict(favorite)
        player.pop("api_metadata", None)
        players.append(player)
    payload = {"schema_version": 1, "real_favorites": players}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def parse_real_favorites(
    payload: bytes | str, *, maximum_players: int = 100
) -> dict[str, dict[str, Any]]:
    """Validate and load a portable real-player favourites file."""
    if isinstance(payload, bytes) and len(payload) > 2_000_000:
        raise ValueError("The favourites file is too large.")
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError("The favourites file is not valid JSON.") from exc
    if not isinstance(parsed, Mapping) or parsed.get("schema_version") != 1:
        raise ValueError("The favourites file uses an unsupported format.")
    players = parsed.get("real_favorites")
    if not isinstance(players, list):
        raise ValueError("The favourites file is missing its player list.")
    if len(players) > maximum_players:
        raise ValueError(
            f"A favourites file can contain at most {maximum_players} players."
        )
    favorites: dict[str, dict[str, Any]] = {}
    for player in players:
        if not isinstance(player, Mapping):
            raise ValueError("Every favourite must be a player object.")
        favorites = save_real_favorite(favorites, player)
    return favorites


def save_league_entry(
    entries: Iterable[Mapping[str, Any]], entry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Add or replace a named mini-league entry and rank highest points first."""
    name = " ".join(str(entry.get("name") or "").split())
    if not name:
        raise ValueError("Give the fantasy team a name.")
    points = entry.get("points")
    try:
        safe_points = float(points)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Fantasy points must be numeric.") from exc
    if not math.isfinite(safe_points):
        raise ValueError("Fantasy points must be finite.")

    normalized = dict(entry)
    normalized["name"] = name[:40]
    normalized["points"] = round(safe_points, 1)
    without_same_name = [
        dict(current)
        for current in entries
        if str(current.get("name") or "").casefold() != name.casefold()
    ]
    without_same_name.append(normalized)
    return sorted(
        without_same_name,
        key=lambda item: (-float(item.get("points") or 0), str(item.get("name") or "")),
    )
