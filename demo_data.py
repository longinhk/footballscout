"""Deterministic fictional scouting catalog for the offline application."""

from __future__ import annotations

import unicodedata
from collections.abc import Collection
from copy import deepcopy
from typing import Any

DATASET_VERSION = "2026.1"
POSITION_ORDER = ("Attacker", "Midfielder", "Defender", "Goalkeeper")

_ROLE_NAMES = {
    "Attacker": (
        "Adrián Vega",
        "Malik Diallo",
        "Lina Okafor",
        "Nia Brooks",
        "Kenji Mori",
        "Mateo Silva",
        "Amara Mensah",
        "Viktor Petrov",
        "Luc Moreau",
        "Sami Haddad",
        "Iker Navarro",
        "Noah Bennett",
    ),
    "Midfielder": (
        "Theo Martins",
        "Maya Chen",
        "Omar Haddad",
        "Sofia Neri",
        "Luka Jovanović",
        "Amina Yusuf",
        "Daniel Kim",
        "Rafael Costa",
        "Elena Petrova",
        "Idris Kane",
        "Chloé Martin",
        "Taro Watanabe",
    ),
    "Defender": (
        "João Costa",
        "Sofia Rojas",
        "Luka Petrović",
        "Aisha Bello",
        "Tomás Ruiz",
        "Elias Berg",
        "Camille Dubois",
        "Riku Tanaka",
        "Jamal Carter",
        "Ana Kovač",
        "Nuno Silva",
        "Priya Nair",
    ),
    "Goalkeeper": (
        "Hana Sato",
        "Mateo Cruz",
        "Leila Mansour",
        "Erik Lund",
        "Chioma Eze",
        "Luca Bianchi",
        "Maya Torres",
        "Elias Novak",
        "Inès Bernard",
        "Jun Park",
        "Daniel Okoro",
        "Sarah Jensen",
    ),
}

_TEAMS = (
    "Solport FC",
    "Harbor United",
    "Northbridge City",
    "Riverside Athletic",
    "Monte Azul",
    "Kestrel 04",
    "Aurora SC",
    "Atlas Borough",
    "Seaside Rovers",
    "Crown Vale",
    "Dynamo Park",
    "Union Sapporo",
)

_LEAGUES = (
    ("Meridian League", 0.86),
    ("Atlantic League", 0.91),
    ("Continental League", 0.96),
    ("Pacific League", 0.88),
)

_NATIONALITIES = (
    "Spain",
    "Senegal",
    "Nigeria",
    "United States",
    "Japan",
    "Brazil",
    "Ghana",
    "Serbia",
    "France",
    "Morocco",
    "Portugal",
    "England",
    "China",
    "Italy",
    "Türkiye",
    "Sweden",
)

_POSITION_DETAILS = {
    "Attacker": ("Centre forward", "Left winger", "Right winger"),
    "Midfielder": ("Central midfielder", "Attacking midfielder", "Holding midfielder"),
    "Defender": ("Centre back", "Left back", "Right back"),
    "Goalkeeper": ("Goalkeeper",),
}

_CURATED_OVERRIDES: dict[str, dict[str, Any]] = {
    "Adrián Vega": {
        "team": "Solport FC",
        "league": "Meridian League",
        "age": 23,
        "games": 30,
        "starts": 28,
        "minutes": 2470,
        "rating": 7.42,
        "goals": 19,
        "assists": 7,
        "shots": 86,
        "key_passes": 34,
        "tackles": 14,
        "interceptions": 4,
        "progressive_actions": 116,
        "pass_accuracy": 78.4,
        "duels_won_pct": 52.8,
        "aerials_won_pct": 47.2,
        "xg": 17.1,
        "xa": 6.3,
        "recent_fee": 24.0,
        "contract_years": 3,
        "injury_risk": "Low",
        "form": [7.18, 7.31, 7.46, 7.55, 7.62, 7.44],
    },
    "Malik Diallo": {
        "team": "Harbor United",
        "league": "Atlantic League",
        "age": 25,
        "games": 32,
        "starts": 30,
        "minutes": 2680,
        "rating": 7.31,
        "goals": 16,
        "assists": 12,
        "shots": 72,
        "key_passes": 52,
        "tackles": 22,
        "interceptions": 9,
        "progressive_actions": 128,
        "pass_accuracy": 81.2,
        "duels_won_pct": 55.1,
        "aerials_won_pct": 51.4,
        "xg": 15.0,
        "xa": 10.4,
        "recent_fee": 28.0,
        "contract_years": 2,
        "injury_risk": "Medium",
        "form": [7.08, 7.24, 7.19, 7.42, 7.51, 7.39],
    },
    "Theo Martins": {
        "team": "Northbridge City",
        "league": "Continental League",
        "age": 21,
        "games": 29,
        "starts": 26,
        "minutes": 2310,
        "rating": 7.55,
        "goals": 9,
        "assists": 14,
        "shots": 58,
        "key_passes": 71,
        "tackles": 48,
        "interceptions": 26,
        "progressive_actions": 176,
        "pass_accuracy": 88.1,
        "duels_won_pct": 57.6,
        "aerials_won_pct": 43.0,
        "xg": 7.6,
        "xa": 12.2,
        "recent_fee": 18.0,
        "contract_years": 4,
        "injury_risk": "Low",
        "form": [7.21, 7.38, 7.61, 7.72, 7.66, 7.75],
    },
    "João Costa": {
        "team": "Riverside Athletic",
        "league": "Pacific League",
        "age": 26,
        "games": 31,
        "starts": 31,
        "minutes": 2760,
        "rating": 7.18,
        "goals": 3,
        "assists": 4,
        "shots": 22,
        "key_passes": 29,
        "tackles": 71,
        "interceptions": 43,
        "clean_sheets": 12,
        "progressive_actions": 98,
        "pass_accuracy": 86.0,
        "duels_won_pct": 64.2,
        "aerials_won_pct": 68.5,
        "xg": 2.1,
        "xa": 3.2,
        "recent_fee": 22.0,
        "contract_years": 2,
        "injury_risk": "Low",
        "form": [7.01, 7.22, 7.14, 7.28, 7.19, 7.25],
    },
}


def _ascii_text(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _form_series(rating: float, index: int) -> list[float]:
    movement = (-0.18, -0.07, 0.03, 0.12, 0.08, 0.21)
    return [
        round(_clamp(rating + shift + ((index % 3) - 1) * 0.025, 6.0, 8.6), 2)
        for shift in movement
    ]


def _make_player(position: str, role_index: int, global_index: int) -> dict[str, Any]:
    name = _ROLE_NAMES[position][role_index]
    team = _TEAMS[role_index]
    league, league_strength = _LEAGUES[role_index % len(_LEAGUES)]
    games = 24 + ((role_index * 3 + global_index) % 10)
    minutes = min(games * 90, games * (70 + (role_index % 5) * 4))
    role_bonus = POSITION_ORDER.index(position) * 0.02
    rating = round(6.78 + (role_index % 7) * 0.11 + role_bonus, 2)
    age = 19 + ((role_index * 2 + global_index) % 14)
    contract_years = 1 + ((role_index + global_index) % 5)

    stats: dict[str, Any] = {
        "goals": 0,
        "assists": 0,
        "conceded": 0,
        "saves": 0,
        "tackles": 0,
        "interceptions": 0,
        "clean_sheets": None,
        "shots": 0,
        "key_passes": 0,
        "xg": 0.0,
        "xa": 0.0,
        "pass_accuracy": round(73.0 + (role_index % 8) * 2.1, 1),
        "duels_won_pct": round(48.0 + (role_index % 7) * 2.2, 1),
        "aerials_won_pct": round(40.0 + (role_index % 8) * 3.1, 1),
        "progressive_actions": 60 + (role_index * 13) % 115,
    }

    if position == "Attacker":
        goals = 8 + (role_index * 3) % 16
        assists = 4 + (role_index * 5) % 10
        stats.update(
            goals=goals,
            assists=assists,
            shots=goals * 3 + 24 + role_index,
            key_passes=assists * 4 + 14,
            xg=round(goals * 0.88, 1),
            xa=round(assists * 0.84, 1),
            tackles=8 + (role_index * 3) % 20,
            interceptions=2 + (role_index * 2) % 10,
            progressive_actions=90 + (role_index * 11) % 70,
        )
    elif position == "Midfielder":
        goals = 3 + (role_index * 3) % 10
        assists = 5 + (role_index * 4) % 12
        stats.update(
            goals=goals,
            assists=assists,
            shots=goals * 3 + 25,
            key_passes=assists * 4 + 24,
            xg=round(goals * 0.82, 1),
            xa=round(assists * 0.86, 1),
            tackles=30 + (role_index * 7) % 43,
            interceptions=16 + (role_index * 5) % 28,
            pass_accuracy=round(82.0 + (role_index % 6) * 1.5, 1),
            progressive_actions=120 + (role_index * 13) % 90,
        )
    elif position == "Defender":
        goals = (role_index * 2) % 6
        assists = 1 + (role_index * 3) % 6
        stats.update(
            goals=goals,
            assists=assists,
            shots=12 + goals * 4,
            key_passes=14 + assists * 4,
            xg=round(goals * 0.74, 1),
            xa=round(assists * 0.78, 1),
            tackles=50 + (role_index * 9) % 48,
            interceptions=31 + (role_index * 7) % 38,
            clean_sheets=6 + (role_index * 3) % 9,
            pass_accuracy=round(81.0 + (role_index % 7) * 1.7, 1),
            duels_won_pct=round(58.0 + (role_index % 7) * 2.0, 1),
            aerials_won_pct=round(55.0 + (role_index % 8) * 3.2, 1),
            progressive_actions=72 + (role_index * 9) % 65,
        )
    else:
        saves = 68 + (role_index * 11) % 62
        conceded = 22 + (role_index * 7) % 27
        stats.update(
            conceded=conceded,
            saves=saves,
            clean_sheets=6 + (role_index * 3) % 10,
            pass_accuracy=round(70.0 + (role_index % 8) * 2.2, 1),
            progressive_actions=42 + (role_index * 8) % 58,
            duels_won_pct=None,
            aerials_won_pct=None,
        )

    injury_risk = ("Low", "Low", "Medium", "Low", "Medium", "High")[
        (role_index + global_index) % 6
    ]
    nationality = _NATIONALITIES[global_index % len(_NATIONALITIES)]
    player = {
        "player_id": f"fs-{position[0].lower()}-{role_index + 1:02d}",
        "name": name,
        "search_aliases": [_ascii_text(name)],
        "photo": None,
        "age": age,
        "nationality": nationality,
        "preferred_foot": "Left" if (role_index + global_index) % 4 == 0 else "Right",
        "height_cm": 172 + ((role_index * 3 + global_index) % 24),
        "team": team,
        "league": league,
        "position": position,
        "position_detail": _POSITION_DETAILS[position][
            role_index % len(_POSITION_DETAILS[position])
        ],
        "games": games,
        "starts": max(0, games - (role_index % 5)),
        "minutes": minutes,
        "rating": rating,
        "scope": league,
        "season": "2025/26",
        "competition_count": 1,
        "contract_years": contract_years,
        "contract_expires": f"{2026 + contract_years}-06-30",
        "injury_risk": injury_risk,
        "games_missed_365": {"Low": 2, "Medium": 6, "High": 12}[injury_risk]
        + role_index % 3,
        "league_strength": league_strength,
        "club_selling_power": round(0.88 + (role_index % 6) * 0.04, 2),
        "recent_fee": round(5.0 + role_index * 2.4 + (3 if age <= 22 else 0), 1),
        "form": _form_series(rating, role_index),
        "data_source": "fictional_offline",
        "dataset_version": DATASET_VERSION,
        **stats,
    }
    player.update(_CURATED_OVERRIDES.get(name, {}))
    player["scope"] = player["league"]
    player["contract_expires"] = f"{2026 + int(player['contract_years'])}-06-30"
    league_lookup = dict(_LEAGUES)
    player["league_strength"] = league_lookup[player["league"]]
    return player


_CATALOG: tuple[dict[str, Any], ...] = tuple(
    _make_player(position, role_index, global_index)
    for global_index, (position, role_index) in enumerate(
        (position, role_index)
        for position in POSITION_ORDER
        for role_index in range(len(_ROLE_NAMES[position]))
    )
)


def all_demo_players() -> list[dict[str, Any]]:
    """Return an isolated copy of the complete offline catalog."""
    return deepcopy(list(_CATALOG))


def demo_player_names() -> list[str]:
    """Return catalog names in deterministic display order."""
    return [player["name"] for player in _CATALOG]


def demo_player_ids() -> list[str]:
    """Return stable catalog identifiers in deterministic display order."""
    return [player["player_id"] for player in _CATALOG]


def catalog_positions() -> list[str]:
    return list(POSITION_ORDER)


def catalog_leagues() -> list[str]:
    return [name for name, _ in _LEAGUES]


def get_demo_player(name: str) -> dict[str, Any]:
    """Return a player by display name for backwards-compatible callers."""
    for player in _CATALOG:
        if player["name"] == name:
            return deepcopy(player)
    raise KeyError(f"Unknown demo player: {name}")


def get_demo_player_by_id(player_id: str) -> dict[str, Any]:
    """Return a player by its stable offline identifier."""
    for player in _CATALOG:
        if player["player_id"] == player_id:
            return deepcopy(player)
    raise KeyError(f"Unknown offline player ID: {player_id}")


def player_label(player_id: str) -> str:
    player = get_demo_player_by_id(player_id)
    return f"{player['name']} · {player['team']} · {player['position']}"


def _normalized_search_text(value: Any) -> str:
    return _ascii_text(str(value or "")).casefold().strip()


def search_demo_players(
    query: str = "",
    *,
    positions: Collection[str] | None = None,
    leagues: Collection[str] | None = None,
    age_range: tuple[int, int] | None = None,
    minimum_minutes: int = 0,
) -> list[dict[str, Any]]:
    """Search and filter the catalog without mutating source records."""
    normalized_query = _normalized_search_text(query)
    position_set = set(positions or ())
    league_set = set(leagues or ())
    minimum_age, maximum_age = age_range or (0, 100)

    matches: list[dict[str, Any]] = []
    for player in _CATALOG:
        searchable = " ".join(
            str(value)
            for value in (
                player["name"],
                *player.get("search_aliases", []),
                player["team"],
                player["league"],
                player["position"],
                player["position_detail"],
                player["nationality"],
            )
        )
        if normalized_query and normalized_query not in _normalized_search_text(
            searchable
        ):
            continue
        if position_set and player["position"] not in position_set:
            continue
        if league_set and player["league"] not in league_set:
            continue
        if not minimum_age <= int(player["age"]) <= maximum_age:
            continue
        if int(player["minutes"]) < int(minimum_minutes):
            continue
        matches.append(deepcopy(player))
    return matches
