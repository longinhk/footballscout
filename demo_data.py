"""Built-in fictional players used for the no-credential demo experience."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_DEMO_PLAYERS: tuple[dict[str, Any], ...] = (
    {
        "name": "Adrián Vega",
        "photo": None,
        "age": 23,
        "team": "Solport FC",
        "league": "Demo League",
        "position": "Attacker",
        "games": 30,
        "minutes": 2470,
        "rating": 7.42,
        "goals": 19,
        "assists": 7,
        "conceded": 0,
        "saves": 0,
        "tackles": 14,
        "interceptions": 4,
        "clean_sheets": None,
        "scope": "Demo League",
        "season": "2025",
        "competition_count": 1,
    },
    {
        "name": "Malik Diallo",
        "photo": None,
        "age": 25,
        "team": "Harbor United",
        "league": "Demo League",
        "position": "Attacker",
        "games": 32,
        "minutes": 2680,
        "rating": 7.31,
        "goals": 16,
        "assists": 12,
        "conceded": 0,
        "saves": 0,
        "tackles": 22,
        "interceptions": 9,
        "clean_sheets": None,
        "scope": "Demo League",
        "season": "2025",
        "competition_count": 1,
    },
    {
        "name": "Theo Martins",
        "photo": None,
        "age": 21,
        "team": "Northbridge City",
        "league": "Demo League",
        "position": "Midfielder",
        "games": 29,
        "minutes": 2310,
        "rating": 7.55,
        "goals": 9,
        "assists": 14,
        "conceded": 0,
        "saves": 0,
        "tackles": 48,
        "interceptions": 26,
        "clean_sheets": None,
        "scope": "Demo League",
        "season": "2025",
        "competition_count": 1,
    },
    {
        "name": "João Costa",
        "photo": None,
        "age": 26,
        "team": "Riverside Athletic",
        "league": "Demo League",
        "position": "Defender",
        "games": 31,
        "minutes": 2760,
        "rating": 7.18,
        "goals": 3,
        "assists": 4,
        "conceded": 27,
        "saves": 0,
        "tackles": 71,
        "interceptions": 43,
        "clean_sheets": 12,
        "scope": "Demo League",
        "season": "2025",
        "competition_count": 1,
    },
)


def demo_player_names() -> list[str]:
    """Return demo player labels in their curated display order."""
    return [player["name"] for player in _DEMO_PLAYERS]


def get_demo_player(name: str) -> dict:
    """Return a copy of one demo player so callers cannot mutate fixtures."""
    for player in _DEMO_PLAYERS:
        if player["name"] == name:
            return deepcopy(player)
    raise KeyError(f"Unknown demo player: {name}")
