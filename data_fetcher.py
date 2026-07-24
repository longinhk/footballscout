"""API-Football client with a stable, testable domain model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://v3.football.api-sports.io"


class FootballAPIError(RuntimeError):
    """An actionable API error safe to show in the UI."""


@dataclass(frozen=True)
class PlayerOption:
    id: int
    name: str
    age: int | None = None
    nationality: str = ""
    photo: str = ""

    @property
    def label(self) -> str:
        details = " · ".join(filter(None, [self.nationality, f"age {self.age}" if self.age else ""]))
        return f"{self.name} ({self.id})" + (f" — {details}" if details else "")


def get_secret(name: str) -> str | None:
    """Read environment first, then Streamlit secrets without noisy missing-file errors."""
    if value := os.getenv(name):
        return value
    locations = (Path.cwd() / ".streamlit/secrets.toml", Path.home() / ".streamlit/secrets.toml")
    if not any(path.is_file() for path in locations):
        return None
    try:
        import streamlit as st

        value = st.secrets.get(name)
        return str(value) if value else None
    except (FileNotFoundError, KeyError):
        return None


class FootballClient:
    def __init__(self, api_key: str, timeout: int = 15, session: requests.Session | None = None):
        if not api_key.strip():
            raise ValueError("An API-Sports key is required.")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{BASE_URL}{path}",
                headers={"x-apisports-key": self.api_key},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise FootballAPIError("API-Football timed out. Please retry.") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            hints = {
                401: "Check that the API key is correct.",
                403: "This key is not authorized. Use a direct API-Sports Football key.",
                429: "The daily API quota or rate limit has been reached.",
            }
            raise FootballAPIError(hints.get(status, f"API-Football returned HTTP {status}.")) from exc
        except (requests.RequestException, ValueError) as exc:
            raise FootballAPIError(f"Could not read API-Football: {exc}") from exc

        errors = payload.get("errors")
        if errors:
            raise FootballAPIError(f"API-Football rejected the request: {errors}")
        return payload

    def search_players(self, query: str) -> list[PlayerOption]:
        query = query.strip()
        if len(query) < 3:
            raise FootballAPIError("Enter at least three characters to search.")
        payload = self._get("/players/profiles", {"search": query})
        options: list[PlayerOption] = []
        for item in payload.get("response") or []:
            player = item.get("player", item)
            if player.get("id") and player.get("name"):
                options.append(
                    PlayerOption(
                        id=int(player["id"]),
                        name=str(player["name"]),
                        age=_optional_int(player.get("age")),
                        nationality=str(player.get("nationality") or ""),
                        photo=str(player.get("photo") or ""),
                    )
                )
        return options

    def player_stats(self, player_id: int, season: int) -> dict[str, Any]:
        payload = self._get("/players", {"id": int(player_id), "season": int(season)})
        return parse_player_stats(payload)


def _optional_int(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None


def _number(value: Any) -> int:
    return int(value or 0)


def parse_player_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize API data and aggregate a player's clubs for the selected season."""
    responses = payload.get("response") or []
    if not responses:
        raise FootballAPIError("No statistics were found for that player and season.")
    try:
        player = responses[0]["player"]
        entries = responses[0]["statistics"]
    except (KeyError, TypeError) as exc:
        raise FootballAPIError("API-Football returned an unexpected data shape.") from exc
    if not entries:
        raise FootballAPIError("The player exists, but has no statistics for that season.")

    def total(group: str, key: str) -> int:
        return sum(_number((entry.get(group) or {}).get(key)) for entry in entries)

    primary = max(entries, key=lambda entry: _number((entry.get("games") or {}).get("minutes")))
    games = primary.get("games") or {}
    ratings = [
        float((entry.get("games") or {}).get("rating"))
        for entry in entries
        if (entry.get("games") or {}).get("rating")
    ]
    return {
        "id": int(player["id"]),
        "name": str(player.get("name") or "Unknown"),
        "photo": str(player.get("photo") or ""),
        "age": _number(player.get("age")),
        "nationality": str(player.get("nationality") or "Unknown"),
        "team": str((primary.get("team") or {}).get("name") or "Unknown"),
        "league": str((primary.get("league") or {}).get("name") or "Unknown"),
        "position": str(games.get("position") or "Unknown"),
        "appearances": total("games", "appearences"),
        "minutes": total("games", "minutes"),
        "rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        "goals": total("goals", "total"),
        "assists": total("goals", "assists"),
        "shots": total("shots", "total"),
        "passes": total("passes", "total"),
        "key_passes": total("passes", "key"),
        "tackles": total("tackles", "total"),
        "interceptions": total("tackles", "interceptions"),
        "duels_won": total("duels", "won"),
        "dribbles": total("dribbles", "success"),
        "clean_sheets": total("games", "cleansheets"),
        "saves": total("goals", "saves"),
        "conceded": total("goals", "conceded"),
    }
