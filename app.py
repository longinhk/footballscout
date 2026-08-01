"""Footy-Scout Streamlit player discovery and comparison workspace."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from app_helpers import (
    comparison_query,
    filter_player_pool,
    filter_profiles,
    parse_comparison_query,
    parse_real_favorites,
    real_favorites_bytes,
    real_result_session_updates,
    save_league_entry,
    toggle_real_favorite_snapshot,
)
from data_fetcher import (
    FootballAPIError,
    fetch_account_status,
    fetch_available_seasons_with_metadata,
    fetch_player_stats,
    get_api_credentials,
    search_player_profiles_with_metadata,
)
from demo_data import (
    DATASET_VERSION,
    all_demo_players,
    catalog_leagues,
    catalog_positions,
    demo_player_ids,
    get_demo_player_by_id,
    player_label,
    search_demo_players,
)
from fantasy import (
    DEFAULT_BUDGET_MILLIONS,
    DEFAULT_SQUAD_SIZE,
    MAX_SQUAD_SIZE,
    calculate_squad,
)
from pdf_report import generate_valuation_pdf
from scouting import (
    add_to_watchlist,
    parse_workspace,
    remove_from_watchlist,
    save_matchup,
    workspace_bytes,
)
from ui_components import (
    APP_CSS,
    comparison_profile_html,
    included_items,
    insights_html,
    masthead_html,
    matchup_html,
    overview_html,
    performance_duel_html,
    player_key_html,
    scouting_profile_html,
    section_header_html,
    sidebar_brand_html,
    sidebar_step_html,
    valuation_lab_html,
)
from valuation import compare_methods, per_90, valuation_confidence


FREE_PLAN_PLAYER_SEASONS = ("2024", "2023", "2022")


st.set_page_config(
    page_title="Footy-Scout",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)
st.html(APP_CSS)


def credential_cache_scope(api_key: str) -> str:
    """Return a non-secret fingerprint so changing accounts invalidates UI caches."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


@st.cache_data(show_spinner=False)
def cached_pdf(
    players: list[dict[str, Any]], valuations: list[dict[str, float]]
) -> bytes:
    return generate_valuation_pdf(players, valuations)


@st.cache_data(ttl=43_200, show_spinner=False)
def cached_profile_search(
    query: str, provider: str, credential_scope: str, _api_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cache global surname searches to protect the owner's daily API quota."""
    return search_player_profiles_with_metadata(
        query, api_key=_api_key, provider=provider
    )


@st.cache_data(ttl=21_600, show_spinner=False)
def cached_real_player(
    player_id: int,
    season: str,
    provider: str,
    credential_scope: str,
    _api_key: str,
) -> dict[str, Any]:
    """Cache season statistics while keeping the server key out of cache hashing."""
    return fetch_player_stats(
        player_id,
        season,
        api_key=_api_key,
        provider=provider,
    )


@st.cache_data(ttl=86_400, show_spinner=False)
def cached_available_seasons(
    provider: str, credential_scope: str, _api_key: str
) -> tuple[list[int], dict[str, Any]]:
    """Load provider-supported seasons once a day, backed by the disk cache."""
    return fetch_available_seasons_with_metadata(
        api_key=_api_key,
        provider=provider,
    )


@st.cache_data(ttl=3_600, show_spinner=False)
def cached_account_status(
    provider: str, credential_scope: str, _api_key: str
) -> dict[str, Any]:
    """Cache the quota-free provider plan check without retaining account PII."""
    return fetch_account_status(api_key=_api_key, provider=provider)


def blended_value(values: dict[str, float]) -> float:
    return sum(values.values()) / len(values)


def optional_per_90(value: Any, minutes: Any) -> float | None:
    """Preserve unavailable feed fields instead of exporting a misleading zero."""
    if value is None:
        return None
    return per_90(value, minutes)


def _report_stem(players: list[dict[str, Any]]) -> str:
    names = "-vs-".join(str(player.get("name") or "player") for player in players)
    ascii_names = (
        unicodedata.normalize("NFKD", names).encode("ascii", "ignore").decode()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_names.lower()).strip("-")
    return f"footy-scout-{slug or 'comparison'}"


def export_frame(
    players: list[dict[str, Any]],
    valuations: list[dict[str, float]],
    blended_values: list[float],
) -> pd.DataFrame:
    """Build an analysis-friendly export for fictional or real season data."""
    rows = []
    for player, values, blended in zip(players, valuations, blended_values):
        confidence = valuation_confidence(player, values)
        recent_form = list(player.get("form") or [])
        rows.append(
            {
                "Player ID": player.get("player_id"),
                "Player": player.get("name"),
                "Team(s)": included_items(player, "teams", "team"),
                "Competition(s)": included_items(player, "competitions", "league"),
                "Season": player.get("season"),
                "Position": player.get("position"),
                "Role": player.get("position_detail"),
                "Age": player.get("age"),
                "Nationality": player.get("nationality"),
                "Preferred foot": player.get("preferred_foot"),
                "Height (cm)": player.get("height_cm"),
                "Appearances": player.get("games"),
                "Starts": player.get("starts"),
                "Minutes": player.get("minutes"),
                "Rating": player.get("rating"),
                "Goals": player.get("goals"),
                "Expected goals": player.get("xg"),
                "Goals per 90": optional_per_90(
                    player.get("goals"), player.get("minutes")
                ),
                "Assists": player.get("assists"),
                "Expected assists": player.get("xa"),
                "Assists per 90": optional_per_90(
                    player.get("assists"), player.get("minutes")
                ),
                "Shots per 90": optional_per_90(
                    player.get("shots"), player.get("minutes")
                ),
                "Key passes per 90": optional_per_90(
                    player.get("key_passes"), player.get("minutes")
                ),
                "Progressive actions per 90": optional_per_90(
                    player.get("progressive_actions"), player.get("minutes")
                ),
                "Pass accuracy %": player.get("pass_accuracy"),
                "Duels won %": player.get("duels_won_pct"),
                "Aerial duels won %": player.get("aerials_won_pct"),
                "Tackles per 90": optional_per_90(
                    player.get("tackles"), player.get("minutes")
                ),
                "Interceptions per 90": optional_per_90(
                    player.get("interceptions"), player.get("minutes")
                ),
                "Saves per 90": optional_per_90(
                    player.get("saves"), player.get("minutes")
                ),
                "Clean sheets": player.get("clean_sheets"),
                "Contract years": player.get("contract_years"),
                "Contract expires": player.get("contract_expires"),
                "Injury risk": player.get("injury_risk"),
                "Games missed (365 days)": player.get("games_missed_365"),
                "League strength": player.get("league_strength"),
                "Club selling power": player.get("club_selling_power"),
                "Recent fee input (EUR M)": player.get("recent_fee"),
                **{
                    f"Recent form {index + 1}": (
                        recent_form[index] if index < len(recent_form) else None
                    )
                    for index in range(6)
                },
                "Heuristic (EUR M)": values.get("Heuristic"),
                "Demo ML (EUR M)": values.get("Demo ML"),
                "Context (EUR M)": values.get("Context"),
                "Blended (EUR M)": blended,
                "Reliability score": confidence["score"],
                "Reliability label": confidence["label"],
                "Scenario low (EUR M)": confidence["low"],
                "Scenario high (EUR M)": confidence["high"],
                "Data source": player.get("data_source"),
                "Dataset version": player.get("dataset_version"),
            }
        )
    return pd.DataFrame(rows)


def watchlist_frame(player_ids: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for player_id in player_ids:
        player = get_demo_player_by_id(player_id)
        values = compare_methods(player)
        confidence = valuation_confidence(player, values)
        rows.append(
            {
                "Player ID": player_id,
                "Player": player["name"],
                "Team": player["team"],
                "Position": player["position"],
                "Age": player["age"],
                "Rating": player["rating"],
                "Blended value (EUR M)": blended_value(values),
                "Reliability": confidence["label"],
            }
        )
    return pd.DataFrame(rows)


def render_methodology(is_real: bool) -> None:
    with st.expander("Methodology & limitations"):
        source_copy = (
            "Player profiles and season statistics come from API-Football. "
            "Coverage can vary by player, competition and season. Contract, fee "
            "and detailed injury context are not provided by this search flow, so "
            "the Context method uses neutral defaults and reliability is reduced."
            if is_real
            else "Every player, club, competition, performance row and fee in the "
            "sample catalog is fictional."
        )
        st.markdown(
            f"""
            - **Heuristic** uses bounded, position-aware per-90 output, age and availability.
            - **Demo ML** is constrained Ridge regression trained on a small synthetic sample.
            - **Context** adjusts the base signal when contract, injury, league, club and fee inputs are available.
            - **Blended estimate** gives all three methods equal weight. The displayed range is illustrative, not a statistical confidence interval.

            {source_copy} All valuations remain educational estimates—not official market values, recruitment recommendations or financial advice.
            """
        )


def render_real_coverage(players: list[dict[str, Any]]) -> None:
    """Explain provider coverage and missing fields for the loaded comparison."""
    tracked_fields = {
        "rating": "rating",
        "shots": "shots",
        "key_passes": "key passes",
        "pass_accuracy": "pass accuracy",
        "duels_won_pct": "duels won",
        "clean_sheets": "clean sheets",
        "progressive_actions": "progressive actions",
    }
    rows = []
    for player in players:
        missing = [
            label
            for field, label in tracked_fields.items()
            if player.get(field) is None
        ]
        rows.append(
            {
                "Player": player.get("name"),
                "Season": player.get("season"),
                "Team coverage": included_items(player, "teams", "team"),
                "Competition coverage": included_items(
                    player, "competitions", "league"
                ),
                "Unavailable fields": ", ".join(missing) if missing else "None",
            }
        )
    with st.expander("Data coverage for this comparison"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(
            "API-Football coverage varies by competition and season. A dash means "
            "the provider did not supply that field; it is never silently changed to zero."
        )


def _toggle_watchlist(player_id: str) -> None:
    current = st.session_state.get("watchlist_ids", [])
    if player_id in current:
        st.session_state["watchlist_ids"] = remove_from_watchlist(current, player_id)
    else:
        st.session_state["watchlist_ids"] = add_to_watchlist(
            current, player_id, set(demo_player_ids())
        )


def _save_current_matchup(first_id: str, second_id: str) -> None:
    st.session_state["saved_matchups"] = save_matchup(
        st.session_state.get("saved_matchups", []), first_id, second_id
    )


def _swap_offline_selection() -> None:
    first_id = st.session_state.get("offline_player_a")
    second_id = st.session_state.get("offline_player_b")
    if first_id and second_id and first_id != second_id:
        st.session_state["offline_player_a"] = second_id
        st.session_state["offline_player_b"] = first_id
        st.session_state["last_valid_ids"] = (second_id, first_id)


def _reset_discovery() -> None:
    st.session_state["offline_search"] = ""
    st.session_state["filter_positions"] = []
    st.session_state["filter_leagues"] = []
    st.session_state["filter_age"] = age_bounds
    st.session_state["filter_minutes"] = 0


def _clear_library() -> None:
    st.session_state["watchlist_ids"] = []
    st.session_state["saved_matchups"] = []


def _load_saved_matchup(matchup: list[str]) -> None:
    _reset_discovery()
    st.session_state["offline_player_a"] = matchup[0]
    st.session_state["offline_player_b"] = matchup[1]
    st.session_state["last_valid_ids"] = tuple(matchup)


def _library_html(player_ids: list[str]) -> str:
    items = []
    for player_id in player_ids:
        player = get_demo_player_by_id(player_id)
        items.append(
            '<div class="fs-library-item">'
            f"<strong>{escape(str(player['name']))}</strong>"
            f"<span>{escape(str(player['team']))} · {escape(str(player['position']))}</span>"
            "</div>"
        )
    return f'<div class="fs-library-list">{"".join(items)}</div>' if items else ""


def _toggle_real_favorite(player: dict[str, Any]) -> None:
    favorites = st.session_state.get("real_favorites", {})
    st.session_state["real_favorites"] = toggle_real_favorite_snapshot(
        favorites, player
    )


def _swap_real_result() -> None:
    result = st.session_state.get("real_result")
    if not result or len(result.get("players", [])) != 2:
        return
    result = dict(result)
    result["players"] = list(reversed(result["players"]))
    st.session_state["real_result"] = result
    first_id = st.session_state.get("real_selected_a")
    second_id = st.session_state.get("real_selected_b")
    if first_id and second_id:
        st.session_state["real_results_a"] = [second_id]
        st.session_state["real_results_b"] = [first_id]
        st.session_state["real_selected_a"] = second_id
        st.session_state["real_selected_b"] = first_id


def _open_fantasy_workspace() -> None:
    st.session_state["workspace_mode"] = "Fantasy challenge"


def _open_compare_workspace() -> None:
    st.session_state["workspace_mode"] = "Compare players"


def _reset_fantasy_filters() -> None:
    st.session_state["fantasy_filter_positions"] = []
    st.session_state["fantasy_filter_nationality"] = ""
    st.session_state["fantasy_filter_club"] = ""
    st.session_state["fantasy_filter_competition"] = ""
    st.session_state["fantasy_filter_age_enabled"] = False


def _sync_fantasy_pool() -> None:
    """Drop stale selections and keep real-favourite squad sizes achievable."""
    st.session_state["fantasy_selected_ids"] = []
    st.session_state.pop("fantasy_captain", None)
    if st.session_state.get("fantasy_pool_mode") == "Real favourites":
        favorites = st.session_state.get("real_favorites", {}).values()
        selected_season = st.session_state.get("fantasy_favorite_season")
        favorite_count = sum(
            1
            for player in favorites
            if selected_season is None
            or str(player.get("season") or "Unknown season") == selected_season
        )
        if favorite_count:
            st.session_state["fantasy_squad_size"] = min(
                int(st.session_state.get("fantasy_squad_size", DEFAULT_SQUAD_SIZE)),
                favorite_count,
                MAX_SQUAD_SIZE,
            )


def _real_library_html(favorites: dict[str, dict[str, Any]]) -> str:
    items = []
    for player in favorites.values():
        teams = included_items(player, "teams", "team")
        items.append(
            '<div class="fs-library-item">'
            f"<strong>{escape(str(player.get('name') or 'Unknown player'))}</strong>"
            f"<span>{escape(teams)} · {escape(str(player.get('position') or 'Unknown'))}</span>"
            "</div>"
        )
    return f'<div class="fs-library-list">{"".join(items)}</div>' if items else ""


def _real_profile_label(api_id: int) -> str:
    profile = st.session_state.get("real_profile_cache", {}).get(str(api_id), {})
    parts = [str(profile.get("name") or f"Player {api_id}")]
    for field in ("position", "nationality"):
        value = str(profile.get(field) or "")
        if value and value != "Unknown":
            parts.append(value)
    if profile.get("age"):
        parts.append(f"Age {profile['age']}")
    return " · ".join(parts)


def _render_real_player_search(
    side: str,
    provider: str,
    api_key: str,
    *,
    positions: list[str],
    nationality: str,
    age_range: tuple[int, int] | None,
) -> int | None:
    title = f"Player {side}"
    term_key = f"real_query_{side.lower()}"
    results_key = f"real_results_{side.lower()}"
    error_key = f"real_error_{side.lower()}"
    selected_key = f"real_selected_{side.lower()}"

    with st.form(f"real_search_form_{side.lower()}"):
        query = st.text_input(
            f"Search {title}",
            key=term_key,
            placeholder="Try Messi, Ronaldo or Mbappé",
        )
        submitted = st.form_submit_button(
            f"Search {title}",
            width="stretch",
        )
    if submitted:
        try:
            with st.spinner(f"Searching for {query.strip() or 'player'}…"):
                results, metadata = cached_profile_search(
                    query,
                    provider,
                    credential_cache_scope(api_key),
                    api_key,
                )
        except FootballAPIError as exc:
            st.session_state[error_key] = str(exc)
            st.session_state[results_key] = []
        else:
            st.session_state[error_key] = ""
            st.session_state[results_key] = [result["api_id"] for result in results]
            profile_cache = dict(st.session_state.get("real_profile_cache", {}))
            profile_cache.update({str(result["api_id"]): result for result in results})
            st.session_state["real_profile_cache"] = profile_cache
            st.session_state["real_api_metadata"] = metadata
            if not results:
                st.session_state[error_key] = (
                    "No matching profiles were found. Try the player's surname."
                )

    error = st.session_state.get(error_key)
    if error:
        st.warning(error)
    raw_result_ids = st.session_state.get(results_key, [])
    profile_cache = st.session_state.get("real_profile_cache", {})
    visible_profiles = filter_profiles(
        [
            profile_cache[str(api_id)]
            for api_id in raw_result_ids
            if str(api_id) in profile_cache
        ],
        positions=positions,
        nationality=nationality,
        age_range=age_range,
    )
    result_ids = [profile["api_id"] for profile in visible_profiles]
    if raw_result_ids and not result_ids:
        st.caption(f"No {title} results match the active profile filters.")
    elif len(result_ids) < len(raw_result_ids):
        st.caption(
            f"Showing {len(result_ids)} of {len(raw_result_ids)} search results."
        )
    if not result_ids:
        return None
    if st.session_state.get(selected_key) not in result_ids:
        st.session_state[selected_key] = result_ids[0]
    return st.selectbox(
        f"{title} result",
        result_ids,
        format_func=_real_profile_label,
        key=selected_key,
        width="stretch",
    )


def _remember_real_players(players: list[dict[str, Any]]) -> None:
    profile_cache = dict(st.session_state.get("real_profile_cache", {}))
    for player in players:
        api_id = player.get("api_id")
        if api_id:
            profile_cache[str(api_id)] = {
                "api_id": api_id,
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "age": player.get("age"),
                "nationality": player.get("nationality"),
                "height_cm": player.get("height_cm"),
                "position": player.get("position"),
                "photo": player.get("photo"),
            }
    st.session_state["real_profile_cache"] = profile_cache


def _store_real_result(
    players: list[dict[str, Any]],
    season: str,
    first_api_id: int,
    second_api_id: int,
    *,
    sync_selectors: bool = False,
) -> None:
    """Store one successful matchup and clear any stale shared-link warning."""
    _remember_real_players(players)
    updates = real_result_session_updates(
        players,
        season,
        first_api_id,
        second_api_id,
        sync_selectors=sync_selectors,
    )
    for key, value in updates.items():
        st.session_state[key] = value


def _load_shared_comparison(
    provider: str,
    api_key: str,
    *,
    allowed_seasons: list[str] | None = None,
) -> None:
    shared = parse_comparison_query(st.query_params)
    if shared is None or st.session_state.get("loaded_share") == shared:
        return
    first_api_id, second_api_id, season = shared
    if allowed_seasons is not None and season not in allowed_seasons:
        st.session_state["shared_comparison_error"] = (
            f"Season {season} is not included in this API plan. Choose one of: "
            f"{', '.join(allowed_seasons)}."
        )
        st.session_state["loaded_share"] = shared
        return
    try:
        with st.spinner("Opening the shared player comparison…"):
            players = [
                cached_real_player(
                    first_api_id,
                    season,
                    provider,
                    credential_cache_scope(api_key),
                    api_key,
                ),
                cached_real_player(
                    second_api_id,
                    season,
                    provider,
                    credential_cache_scope(api_key),
                    api_key,
                ),
            ]
    except FootballAPIError as exc:
        st.session_state["shared_comparison_error"] = str(exc)
    else:
        _store_real_result(
            players,
            season,
            first_api_id,
            second_api_id,
            sync_selectors=True,
        )
    finally:
        st.session_state["loaded_share"] = shared


def render_real_setup(
    credentials: tuple[str, str] | None,
) -> tuple[list[dict[str, Any]] | None, str]:
    st.html(sidebar_step_html(1, "Search real players", "Global surname search"))
    if credentials is None:
        st.error(
            "Real-player search needs a server API_FOOTBALL_KEY. Visitors never "
            "see or enter this key."
        )
        st.link_button(
            "Get an API-Football key",
            "https://dashboard.api-football.com/register",
            width="stretch",
        )
        st.caption("After setup, visitors can search names such as Messi.")
        return None, "Real players · setup required"

    provider, api_key = credentials
    try:
        account_status = cached_account_status(
            provider, credential_cache_scope(api_key), api_key
        )
    except FootballAPIError as exc:
        account_status = {}
        st.warning(f"The API plan status could not be checked. {exc}")

    fallback_seasons = [
        str(year) for year in range(date.today().year, date.today().year - 5, -1)
    ]
    is_free_plan = str(account_status.get("plan") or "").casefold() == "free"
    try:
        available_seasons, season_metadata = cached_available_seasons(
            provider, credential_cache_scope(api_key), api_key
        )
    except FootballAPIError as exc:
        st.warning(f"Available seasons could not be refreshed. {exc}")
        season_options = (
            list(FREE_PLAN_PLAYER_SEASONS) if is_free_plan else fallback_seasons
        )
    else:
        if is_free_plan:
            season_options = [
                str(season)
                for season in available_seasons
                if str(season) in FREE_PLAN_PLAYER_SEASONS
            ]
            if not season_options:
                season_options = list(FREE_PLAN_PLAYER_SEASONS)
        else:
            season_options = [
                str(season)
                for season in available_seasons
                if season <= date.today().year
            ][:10]
        st.session_state["real_api_metadata"] = season_metadata
        if not season_options:
            season_options = fallback_seasons

    shared_request = parse_comparison_query(st.query_params)
    if (
        shared_request is not None
        and st.session_state.get("loaded_share") != shared_request
    ):
        first_api_id, second_api_id, shared_season = shared_request
        st.caption(
            "Shared comparison ready · "
            f"players {first_api_id} and {second_api_id} · season {shared_season}"
        )
        if st.button(
            "Load shared comparison",
            type="primary",
            key="load_shared_comparison",
            width="stretch",
        ):
            _load_shared_comparison(
                provider,
                api_key,
                allowed_seasons=season_options,
            )
    shared_error = st.session_state.get("shared_comparison_error")
    if shared_error:
        st.warning(f"The shared comparison could not be opened. {shared_error}")
    requested_season = st.session_state.get("real_season")
    if requested_season and requested_season not in season_options and not is_free_plan:
        season_options.insert(0, str(requested_season))
    season = st.selectbox(
        "Season",
        season_options,
        key="real_season",
        help="European 2025/26 competitions use season 2025.",
    )
    if is_free_plan:
        st.caption("Free-plan player statistics currently cover seasons 2022–2024.")
    quota = st.session_state.get("real_api_metadata", {}).get("quota", {})
    if quota.get("remaining") is not None:
        st.caption(
            f"API allowance: {quota['remaining']} of {quota.get('limit', '—')} "
            "requests remaining today"
        )
    with st.expander("Real-player filters"):
        selected_positions = st.multiselect(
            "Profile positions",
            ["Goalkeeper", "Defender", "Midfielder", "Attacker"],
            key="real_filter_positions",
            placeholder="All positions",
        )
        nationality = st.text_input(
            "Nationality contains",
            key="real_filter_nationality",
            placeholder="For example Argentina",
        )
        use_age_filter = st.toggle("Use age filter", key="real_filter_age_enabled")
        selected_age = (
            st.slider(
                "Profile age range",
                min_value=15,
                max_value=60,
                value=(18, 40),
                key="real_filter_age",
            )
            if use_age_filter
            else None
        )
        st.caption(
            "Filters apply locally to fetched profiles, so they use no extra requests."
        )
    st.caption("Search full names or surnames · minimum 4 characters · cached")
    st.html(sidebar_step_html(2, "Choose the matchup", "Search each player"))
    first_api_id = _render_real_player_search(
        "A",
        provider,
        api_key,
        positions=selected_positions,
        nationality=nationality,
        age_range=selected_age,
    )
    second_api_id = _render_real_player_search(
        "B",
        provider,
        api_key,
        positions=selected_positions,
        nationality=nationality,
        age_range=selected_age,
    )
    st.html(player_key_html())

    can_compare = first_api_id is not None and second_api_id is not None
    if can_compare and first_api_id == second_api_id:
        st.error("Choose two different real players.")
        can_compare = False
    compare = st.button(
        "Compare selected players",
        type="primary",
        disabled=not can_compare,
        key="compare_real_players",
        width="stretch",
    )
    if compare and first_api_id is not None and second_api_id is not None:
        try:
            with st.spinner(f"Loading {season} season statistics…"):
                real_players = [
                    cached_real_player(
                        first_api_id,
                        season,
                        provider,
                        credential_cache_scope(api_key),
                        api_key,
                    ),
                    cached_real_player(
                        second_api_id,
                        season,
                        provider,
                        credential_cache_scope(api_key),
                        api_key,
                    ),
                ]
        except FootballAPIError as exc:
            st.error(str(exc))
        else:
            _store_real_result(real_players, season, first_api_id, second_api_id)
            st.session_state["loaded_share"] = (
                first_api_id,
                second_api_id,
                str(season),
            )
            st.query_params.from_dict(
                comparison_query((first_api_id, second_api_id), season)
            )

    st.html(sidebar_step_html(3, "Read the comparison", "Change names anytime"))
    saved_result = st.session_state.get("real_result")
    favorites = st.session_state.get("real_favorites", {})
    with st.expander(
        f"Real-player favourites ({len(favorites)})", expanded=bool(favorites)
    ):
        import_notice = st.session_state.pop("real_favorites_notice", None)
        if import_notice:
            st.success(import_notice)
        if favorites:
            st.html(_real_library_html(favorites))
            st.caption("Use these saved players in the Fantasy Challenge.")
            st.download_button(
                "Download real-player favourites",
                data=real_favorites_bytes(favorites),
                file_name="footy-scout-real-favourites.json",
                mime="application/json",
                on_click="ignore",
                key="download_real_favorites",
                width="stretch",
            )
        else:
            st.caption("Compare real players, then save them for fantasy squads.")
        uploaded_favorites = st.file_uploader(
            "Import real-player favourites",
            type=["json"],
            key="real_favorites_upload",
        )
        if uploaded_favorites is None:
            st.session_state.pop("real_favorites_upload_digest", None)
        else:
            payload = uploaded_favorites.getvalue()
            upload_digest = hashlib.sha256(payload).hexdigest()
            if upload_digest != st.session_state.get("real_favorites_upload_digest"):
                try:
                    imported_favorites = parse_real_favorites(payload)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["real_favorites"] = imported_favorites
                    st.session_state["real_favorites_upload_digest"] = upload_digest
                    st.session_state["real_favorites_notice"] = (
                        "Real-player favourites imported."
                    )
                    st.rerun()
    if not saved_result:
        return None, f"API-Football · season {season}"
    return saved_result["players"], f"API-Football · season {saved_result['season']}"


def render_offline_setup() -> tuple[list[dict[str, Any]], str]:
    st.html(sidebar_step_html(1, "Explore samples", "Search fictional profiles"))
    search_query = st.text_input(
        "Search sample players",
        key="offline_search",
        placeholder="Player, club, league or country",
    )
    with st.expander("Sample filters"):
        selected_positions = st.multiselect(
            "Positions",
            catalog_positions(),
            key="filter_positions",
            placeholder="All positions",
        )
        selected_leagues = st.multiselect(
            "Leagues",
            catalog_leagues(),
            key="filter_leagues",
            placeholder="All leagues",
        )
        selected_age = st.slider(
            "Age range",
            min_value=age_bounds[0],
            max_value=age_bounds[1],
            key="filter_age",
        )
        minimum_minutes = st.slider(
            "Minimum minutes",
            min_value=0,
            max_value=3000,
            step=300,
            key="filter_minutes",
        )
        st.button(
            "Reset sample filters",
            key="reset_filters",
            on_click=_reset_discovery,
            width="stretch",
        )

    filtered_players = search_demo_players(
        search_query,
        positions=selected_positions,
        leagues=selected_leagues,
        age_range=selected_age,
        minimum_minutes=minimum_minutes,
    )
    filtered_ids = [player["player_id"] for player in filtered_players]
    st.caption(f"{len(filtered_ids)} of {len(roster)} sample players match")
    st.html(sidebar_step_html(2, "Build the matchup", "Pick a player and opponent"))

    if filtered_ids:
        first_was_filtered_out = (
            st.session_state.get("offline_player_a") not in filtered_ids
        )
        if first_was_filtered_out:
            st.session_state["offline_player_a"] = filtered_ids[0]
        first_id = st.selectbox(
            "Player A",
            filtered_ids,
            format_func=player_label,
            key="offline_player_a",
            width="stretch",
        )
        if len(filtered_ids) == 1:
            second_options = [
                player_id for player_id in valid_ids if player_id != first_id
            ]
            st.caption("One sample match · choose its opponent from all samples")
        else:
            second_options = filtered_ids
        if st.session_state.get("offline_player_b") not in second_options or (
            first_was_filtered_out
            and st.session_state.get("offline_player_b") == first_id
        ):
            st.session_state["offline_player_b"] = next(
                player_id for player_id in second_options if player_id != first_id
            )
        second_id = st.selectbox(
            "Player B",
            second_options,
            format_func=player_label,
            key="offline_player_b",
            width="stretch",
        )
        if first_id == second_id:
            st.error("Choose two different players. Keeping the last valid matchup.")
        else:
            st.session_state["last_valid_ids"] = (first_id, second_id)
    else:
        st.warning("No samples match. Broaden the search or reset the filters.")

    result_ids = tuple(st.session_state.get("last_valid_ids", default_pair))
    if (
        len(result_ids) != 2
        or result_ids[0] not in valid_ids
        or result_ids[1] not in valid_ids
        or result_ids[0] == result_ids[1]
    ):
        result_ids = default_pair
        st.session_state["last_valid_ids"] = default_pair
    players = [get_demo_player_by_id(player_id) for player_id in result_ids]
    st.html(player_key_html())

    st.html(sidebar_step_html(3, "Keep your shortlist", "Stored in this session"))
    with st.expander(
        f"Sample workspace ({len(st.session_state['watchlist_ids'])})",
        expanded=bool(st.session_state["watchlist_ids"]),
    ):
        import_notice = st.session_state.pop("workspace_import_notice", None)
        if import_notice:
            st.success(import_notice)
        watchlist_ids = st.session_state["watchlist_ids"]
        if watchlist_ids:
            st.html(_library_html(watchlist_ids))
            st.download_button(
                "Download watchlist CSV",
                data=watchlist_frame(watchlist_ids).to_csv(index=False).encode("utf-8"),
                file_name="footy-scout-watchlist.csv",
                mime="text/csv",
                on_click="ignore",
                key="download_watchlist",
                width="stretch",
            )
        else:
            st.caption("No sample players saved yet.")

        saved_matchups = st.session_state["saved_matchups"]
        if saved_matchups:
            matchup_index = st.selectbox(
                "Saved sample matchups",
                range(len(saved_matchups)),
                format_func=lambda index: (
                    f"{get_demo_player_by_id(saved_matchups[index][0])['name']} vs "
                    f"{get_demo_player_by_id(saved_matchups[index][1])['name']}"
                ),
                key="saved_matchup_choice",
            )
            st.button(
                "Load saved matchup",
                on_click=_load_saved_matchup,
                args=(saved_matchups[matchup_index],),
                key="load_matchup",
                width="stretch",
            )

        portable_workspace = workspace_bytes(watchlist_ids, saved_matchups)
        st.download_button(
            "Download sample workspace",
            data=portable_workspace,
            file_name="footy-scout-sample-workspace.json",
            mime="application/json",
            on_click="ignore",
            key="download_sidebar_workspace",
            width="stretch",
        )
        uploaded_workspace = st.file_uploader(
            "Import sample workspace",
            type=["json"],
            key="workspace_upload",
        )
        if uploaded_workspace is None:
            st.session_state.pop("workspace_upload_digest", None)
        else:
            payload = uploaded_workspace.getvalue()
            upload_digest = hashlib.sha256(payload).hexdigest()
            if upload_digest != st.session_state.get("workspace_upload_digest"):
                try:
                    imported_watchlist, imported_matchups = parse_workspace(
                        payload, set(valid_ids)
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["watchlist_ids"] = imported_watchlist
                    st.session_state["saved_matchups"] = imported_matchups
                    st.session_state["workspace_upload_digest"] = upload_digest
                    st.session_state["workspace_import_notice"] = (
                        "Sample workspace imported."
                    )
                    st.rerun()
        if watchlist_ids or saved_matchups:
            st.button(
                "Clear sample workspace",
                on_click=_clear_library,
                key="clear_library",
                width="stretch",
            )
    st.caption("Fictional samples for trying the interface without a data key")
    return players, f"Sample catalog · {len(roster)} players · v{DATASET_VERSION}"


def _fantasy_player_label(player_id: str, pool: dict[str, dict[str, Any]]) -> str:
    player = pool[player_id]
    team = included_items(player, "teams", "team")
    return (
        f"{player.get('name') or 'Unknown player'} · "
        f"{team} · {player.get('position') or 'Unknown'}"
    )


def _fantasy_season(player: dict[str, Any]) -> str:
    return str(player.get("season") or "Unknown season")


def render_fantasy_sidebar() -> dict[str, Any]:
    st.html(sidebar_step_html(1, "Choose the player pool", "Samples or favourites"))
    pool_mode = st.segmented_control(
        "Fantasy player pool",
        ("Sample catalog", "Real favourites"),
        key="fantasy_pool_mode",
        on_change=_sync_fantasy_pool,
        width="stretch",
    )
    if pool_mode == "Real favourites":
        favorites = {
            str(player_id): dict(player)
            for player_id, player in st.session_state["real_favorites"].items()
        }
        known_seasons = sorted(
            {
                _fantasy_season(player)
                for player in favorites.values()
                if _fantasy_season(player) != "Unknown season"
            },
            reverse=True,
        )
        if any(
            _fantasy_season(player) == "Unknown season" for player in favorites.values()
        ):
            known_seasons.append("Unknown season")
        if known_seasons:
            if st.session_state.get("fantasy_favorite_season") not in known_seasons:
                st.session_state["fantasy_favorite_season"] = known_seasons[0]
            selected_favorite_season = st.selectbox(
                "Favourite season",
                known_seasons,
                index=None,
                key="fantasy_favorite_season",
                on_change=_sync_fantasy_pool,
                help="Real-player fantasy squads use one season so scores are comparable.",
            )
            unfiltered_pool = {
                player_id: player
                for player_id, player in favorites.items()
                if _fantasy_season(player) == selected_favorite_season
            }
            st.caption(f"Scoring saved season {selected_favorite_season}")
            if unfiltered_pool:
                st.session_state["fantasy_squad_size"] = min(
                    int(st.session_state.get("fantasy_squad_size", DEFAULT_SQUAD_SIZE)),
                    len(unfiltered_pool),
                    MAX_SQUAD_SIZE,
                )
        else:
            unfiltered_pool = favorites
    else:
        unfiltered_pool = {player["player_id"]: player for player in roster}

    with st.expander("Fantasy pool filters"):
        available_positions = sorted(
            {
                str(player.get("position"))
                for player in unfiltered_pool.values()
                if player.get("position")
            }
        )
        fantasy_positions = st.multiselect(
            "Fantasy positions",
            available_positions,
            key="fantasy_filter_positions",
            placeholder="All positions",
        )
        fantasy_nationality = st.text_input(
            "Fantasy nationality contains",
            key="fantasy_filter_nationality",
        )
        fantasy_club = st.text_input("Club contains", key="fantasy_filter_club")
        fantasy_competition = st.text_input(
            "League or competition contains",
            key="fantasy_filter_competition",
        )
        fantasy_age_enabled = st.toggle(
            "Use fantasy age filter", key="fantasy_filter_age_enabled"
        )
        fantasy_age = (
            st.slider(
                "Fantasy age range",
                min_value=15,
                max_value=60,
                value=(18, 40),
                key="fantasy_filter_age",
            )
            if fantasy_age_enabled
            else None
        )
        st.button(
            "Reset fantasy filters",
            on_click=_reset_fantasy_filters,
            key="reset_fantasy_filters",
            width="stretch",
        )
    filtered_pool = filter_player_pool(
        unfiltered_pool.values(),
        positions=fantasy_positions,
        nationality=fantasy_nationality,
        club=fantasy_club,
        competition=fantasy_competition,
        age_range=fantasy_age,
    )
    pool = {str(player["player_id"]): player for player in filtered_pool}
    if unfiltered_pool:
        st.caption(f"{len(pool)} of {len(unfiltered_pool)} fantasy players match")

    if not unfiltered_pool:
        st.warning("Save real players from a comparison before building this squad.")
        st.button(
            "Return to real-player search",
            on_click=_open_compare_workspace,
            key="fantasy_to_compare",
            width="stretch",
        )
    elif not pool:
        st.warning("No fantasy players match the active filters.")

    st.html(sidebar_step_html(2, "Build a squad", "Choose 1–8 players"))
    squad_size = st.slider(
        "Squad size",
        min_value=1,
        max_value=MAX_SQUAD_SIZE,
        key="fantasy_squad_size",
    )
    pool_ids = list(pool)
    selected_state = [
        player_id
        for player_id in st.session_state.get("fantasy_selected_ids", [])
        if player_id in pool
    ][:squad_size]
    if selected_state != st.session_state.get("fantasy_selected_ids", []):
        st.session_state["fantasy_selected_ids"] = selected_state
    selected_ids = st.multiselect(
        f"Select exactly {squad_size} player{'s' if squad_size != 1 else ''}",
        pool_ids,
        format_func=lambda player_id: _fantasy_player_label(player_id, pool),
        max_selections=squad_size,
        key="fantasy_selected_ids",
        placeholder="Add players to the squad",
    )
    captain_id: str | None = None
    if selected_ids:
        if st.session_state.get("fantasy_captain") not in selected_ids:
            st.session_state["fantasy_captain"] = selected_ids[0]
        captain_id = st.selectbox(
            "Captain · scores double points",
            selected_ids,
            format_func=lambda player_id: _fantasy_player_label(player_id, pool),
            key="fantasy_captain",
        )

    selected_players = [pool[player_id] for player_id in selected_ids]
    squad = calculate_squad(
        selected_players,
        captain_id,
        squad_size=squad_size,
        budget=DEFAULT_BUDGET_MILLIONS,
    )
    st.html(sidebar_step_html(3, "Enter the mini league", "Save this lineup"))
    team_name = st.text_input(
        "Fantasy team name",
        key="fantasy_team_name",
        max_chars=40,
        placeholder="For example Harbour XI",
    )
    save_squad = st.button(
        "Save team to leaderboard",
        type="primary",
        disabled=not squad["is_valid"] or not team_name.strip(),
        key="save_fantasy_team",
        width="stretch",
    )
    if save_squad:
        captain_name = next(
            (row["name"] for row in squad["players"] if row.get("is_captain")),
            "Unknown",
        )
        entry = {
            "name": team_name,
            "points": squad["total_points"],
            "value": squad["total_value"],
            "captain": captain_name,
            "players": ", ".join(row["name"] for row in squad["players"]),
            "source": pool_mode,
            "season": ", ".join(
                sorted(
                    {
                        str(row.get("season"))
                        for row in squad["players"]
                        if row.get("season")
                    }
                )
            )
            or "Unknown",
        }
        st.session_state["fantasy_league"] = save_league_entry(
            st.session_state["fantasy_league"], entry
        )
        st.session_state["fantasy_notice"] = f"{team_name.strip()} joined the league."

    st.caption("Educational season-total scoring · stored in this session")
    return {"pool_mode": pool_mode, "squad": squad, "squad_size": squad_size}


def render_fantasy_main(context: dict[str, Any]) -> None:
    squad = context["squad"]
    pool_mode = context["pool_mode"]
    st.html(masthead_html(f"Fantasy Challenge · {pool_mode}"))
    st.title("Build your squad. Chase the points.")
    st.html(
        """
        <p class="fs-deck">
          Create a one-to-eight-player lineup under a €100M budget, name a
          captain for double points and place the team on your session leaderboard.
        </p>
        """
    )

    notice = st.session_state.pop("fantasy_notice", None)
    if notice:
        st.success(notice)

    metric_columns = st.columns(4)
    metric_columns[0].metric("Squad points", squad["total_points"])
    metric_columns[1].metric("Squad value", f"€{squad['total_value']:.1f}M")
    remaining = squad.get("budget_remaining")
    metric_columns[2].metric(
        "Budget remaining",
        f"€{remaining:.1f}M" if remaining is not None else "—",
    )
    metric_columns[3].metric(
        "Players", f"{squad['player_count']} / {context['squad_size']}"
    )

    if squad["errors"] and squad["player_count"]:
        st.warning("\n\n".join(f"• {error}" for error in squad["errors"]))
    elif not squad["player_count"]:
        st.info("Choose players in the sidebar to start the Fantasy Challenge.")

    if squad["players"]:
        squad_rows = [
            {
                "Player": f"{row['name']}{' (C)' if row['is_captain'] else ''}",
                "Position": row["position"],
                "Season": row.get("season") or "Unknown",
                "Price (EUR M)": row["price"],
                "Base points": row["base_points"],
                "Multiplier": f"×{row['multiplier']}",
                "Fantasy points": row["points"],
            }
            for row in squad["players"]
        ]
        st.html(
            section_header_html(
                "Squad sheet",
                "Your selected lineup",
                "Captain points are doubled",
            )
        )
        st.dataframe(
            pd.DataFrame(squad_rows),
            hide_index=True,
            width="stretch",
        )

    with st.expander("Fantasy scoring rules"):
        st.markdown(
            """
            - Appearance and 60-minute-equivalent points reward availability.
            - Goals are worth more for goalkeepers and defenders; assists are worth three.
            - Goalkeepers earn save points, while defensive roles receive clean-sheet points.
            - Cards and goals conceded can reduce the total; strong ratings add a small bonus.
            - The captain scores double. Prices compress the educational valuation into a €4M–€25M fantasy range.

            Scores use season totals and are a product demonstration, not an official fantasy competition.
            """
        )

    league_entries = st.session_state["fantasy_league"]
    st.html(
        section_header_html(
            "Mini league",
            "Session leaderboard",
            "Save another named lineup to compete",
        )
    )
    if league_entries:
        league_frame = pd.DataFrame(
            [
                {
                    "Rank": index,
                    "Team": entry["name"],
                    "Points": entry["points"],
                    "Value (EUR M)": entry.get("value"),
                    "Captain": entry.get("captain"),
                    "Player pool": entry.get("source"),
                    "Season": entry.get("season"),
                }
                for index, entry in enumerate(league_entries, start=1)
            ]
        )
        st.dataframe(league_frame, hide_index=True, width="stretch")
        st.download_button(
            "Download leaderboard CSV",
            data=league_frame.to_csv(index=False).encode("utf-8"),
            file_name="footy-scout-fantasy-leaderboard.csv",
            mime="text/csv",
            on_click="ignore",
            key="download_fantasy_league",
        )
    else:
        st.caption("No fantasy teams have joined this session yet.")


roster = all_demo_players()
valid_ids = demo_player_ids()
default_pair = (valid_ids[0], valid_ids[1])
ages = [int(player["age"]) for player in roster]
age_bounds = (min(ages), max(ages))

st.session_state.setdefault("watchlist_ids", [])
st.session_state.setdefault("saved_matchups", [])
st.session_state.setdefault("last_valid_ids", default_pair)
st.session_state.setdefault("offline_player_a", default_pair[0])
st.session_state.setdefault("offline_player_b", default_pair[1])
st.session_state.setdefault("offline_search", "")
st.session_state.setdefault("filter_positions", [])
st.session_state.setdefault("filter_leagues", [])
st.session_state.setdefault("filter_age", age_bounds)
st.session_state.setdefault("filter_minutes", 0)
st.session_state.setdefault("real_profile_cache", {})
st.session_state.setdefault("real_favorites", {})
st.session_state.setdefault("fantasy_league", [])
st.session_state.setdefault("workspace_mode", "Compare players")
st.session_state.setdefault("fantasy_pool_mode", "Sample catalog")
st.session_state.setdefault("fantasy_squad_size", DEFAULT_SQUAD_SIZE)

credentials = get_api_credentials()
players: list[dict[str, Any]] | None
fantasy_context: dict[str, Any] | None = None
with st.sidebar:
    st.html(sidebar_brand_html())
    workspace_mode = st.segmented_control(
        "Workspace",
        ("Compare players", "Fantasy challenge"),
        key="workspace_mode",
        width="stretch",
    )
    if workspace_mode == "Fantasy challenge":
        fantasy_context = render_fantasy_sidebar()
        source_mode = None
        players = None
        source_note = "Fantasy Challenge"
    else:
        source_mode = st.segmented_control(
            "Player source",
            ("Real players", "Sample catalog"),
            default="Real players",
            key="source_mode",
            width="stretch",
        )
        if source_mode == "Sample catalog":
            players, source_note = render_offline_setup()
        else:
            players, source_note = render_real_setup(credentials)

if workspace_mode == "Fantasy challenge" and fantasy_context is not None:
    render_fantasy_main(fantasy_context)
    st.stop()

is_real = source_mode == "Real players"
st.html(masthead_html(source_note))
st.title("Compare the season. See the edge.")
if is_real:
    st.html(
        """
        <p class="fs-deck">
          Search real players from around the world by name, load a season and
          compare their output on the same scouting canvas.
        </p>
        """
    )
else:
    st.html(
        """
        <p class="fs-deck">
          Explore the fictional sample catalog, compare role profiles and try the
          full interface without using the site owner's data quota.
        </p>
        """
    )

if players is None:
    if credentials is None:
        st.info(
            "The interface is ready, but the site owner must configure one "
            "API_FOOTBALL_KEY before visitors can search real players."
        )
    else:
        st.info(
            "Search Player A and Player B in the sidebar, choose one result for "
            "each, then run the comparison."
        )
    render_methodology(is_real=True)
    st.stop()

valuations = [compare_methods(player) for player in players]
blended_values = [blended_value(values) for values in valuations]
st.html(matchup_html(players, valuations, blended_values))

if is_real:
    with st.container(key="action_tray"):
        first_favorite, second_favorite, share_column, fantasy_column = st.columns(4)
        favorite_ids = st.session_state["real_favorites"]
        with first_favorite:
            first_snapshot = favorite_ids.get(players[0]["player_id"])
            first_saved = first_snapshot is not None
            first_same_season = first_saved and str(
                first_snapshot.get("season")
            ) == str(players[0].get("season"))
            st.button(
                (
                    "Remove favourite A"
                    if first_same_season
                    else "Update favourite A" if first_saved else "Favourite Player A"
                ),
                on_click=_toggle_real_favorite,
                args=(players[0],),
                key="toggle_real_favorite_a",
                width="stretch",
            )
        with second_favorite:
            second_snapshot = favorite_ids.get(players[1]["player_id"])
            second_saved = second_snapshot is not None
            second_same_season = second_saved and str(
                second_snapshot.get("season")
            ) == str(players[1].get("season"))
            st.button(
                (
                    "Remove favourite B"
                    if second_same_season
                    else "Update favourite B" if second_saved else "Favourite Player B"
                ),
                on_click=_toggle_real_favorite,
                args=(players[1],),
                key="toggle_real_favorite_b",
                width="stretch",
            )
        with share_column:
            if st.button(
                "Make shareable link", key="share_real_comparison", width="stretch"
            ):
                st.session_state["loaded_share"] = (
                    int(players[0]["api_id"]),
                    int(players[1]["api_id"]),
                    str(players[0]["season"]),
                )
                st.query_params.from_dict(
                    comparison_query(
                        (players[0]["api_id"], players[1]["api_id"]),
                        players[0]["season"],
                    )
                )
                st.toast("The browser address now opens this comparison.")
        with fantasy_column:
            st.button(
                "Open Fantasy Challenge",
                on_click=_open_fantasy_workspace,
                key="open_fantasy",
                width="stretch",
            )
else:
    with st.container(key="action_tray"):
        first_watchlist, second_watchlist, save_column, swap_column = st.columns(4)
        with first_watchlist:
            first_saved = players[0]["player_id"] in st.session_state["watchlist_ids"]
            st.button(
                "Remove Player A" if first_saved else "Watch Player A",
                on_click=_toggle_watchlist,
                args=(players[0]["player_id"],),
                key="toggle_watchlist_a",
                width="stretch",
            )
        with second_watchlist:
            second_saved = players[1]["player_id"] in st.session_state["watchlist_ids"]
            st.button(
                "Remove Player B" if second_saved else "Watch Player B",
                on_click=_toggle_watchlist,
                args=(players[1]["player_id"],),
                key="toggle_watchlist_b",
                width="stretch",
            )
        with save_column:
            st.button(
                "Save matchup",
                on_click=_save_current_matchup,
                args=(players[0]["player_id"], players[1]["player_id"]),
                key="save_matchup",
                width="stretch",
            )
        with swap_column:
            st.button(
                "Swap A / B",
                on_click=_swap_offline_selection,
                key="swap_players",
                width="stretch",
            )

st.html(
    section_header_html(
        "Season overview",
        "The essentials, aligned",
        "Availability, form and context in one glance",
    )
)
st.html(overview_html(players))
st.html(
    section_header_html(
        "Quick read",
        "Where the edge shows up",
        "Directional signals, not a scouting verdict",
    )
)
st.html(insights_html(players))

if is_real:
    st.html(
        section_header_html(
            "Comparison profile",
            "Role signals at a glance",
            "Season metrics normalized inside this matchup",
        )
    )
    st.html(comparison_profile_html(players))
else:
    st.html(
        section_header_html(
            "Scouting profile",
            "Role signals at a glance",
            "Percentiles use 12-player fictional position cohorts",
        )
    )
    st.html(scouting_profile_html(players, roster))

st.html(
    section_header_html(
        "Performance duel",
        "Output in context",
        "Per-90 rates normalize playing time",
    )
)
st.html(performance_duel_html(players))
if is_real:
    render_real_coverage(players)
st.html(
    section_header_html(
        "Valuation lab",
        "Three transparent lenses",
        "Educational models · equal-weight blend",
    )
)
st.html(valuation_lab_html(players, valuations))
render_methodology(is_real)

comparison_export = export_frame(players, valuations, blended_values)
stem = _report_stem(players)
if is_real:
    with st.container(key="export_tray"):
        intro, pdf_column, csv_column = st.columns(
            [1.65, 1, 1], gap="medium", vertical_alignment="center"
        )
        with intro:
            st.subheader("Take the comparison with you")
            st.caption("Share the report or analyze the season rows.")
        with pdf_column:
            st.download_button(
                "Download PDF",
                data=cached_pdf(players, valuations),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                type="primary",
                on_click="ignore",
                key="download_pdf",
                width="stretch",
            )
        with csv_column:
            st.download_button(
                "Download CSV",
                data=comparison_export.to_csv(index=False).encode("utf-8"),
                file_name=f"{stem}.csv",
                mime="text/csv",
                on_click="ignore",
                key="download_csv",
                width="stretch",
            )
else:
    portable_workspace = workspace_bytes(
        st.session_state["watchlist_ids"], st.session_state["saved_matchups"]
    )
    with st.container(key="export_tray"):
        intro, pdf_column, csv_column, json_column = st.columns(
            [1.55, 1, 1, 1], gap="medium", vertical_alignment="center"
        )
        with intro:
            st.subheader("Take the sample work with you")
            st.caption("Share, analyze or resume the fictional shortlist later.")
        with pdf_column:
            st.download_button(
                "Download PDF",
                data=cached_pdf(players, valuations),
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                type="primary",
                on_click="ignore",
                key="download_pdf",
                width="stretch",
            )
        with csv_column:
            st.download_button(
                "Download CSV",
                data=comparison_export.to_csv(index=False).encode("utf-8"),
                file_name=f"{stem}.csv",
                mime="text/csv",
                on_click="ignore",
                key="download_csv",
                width="stretch",
            )
        with json_column:
            st.download_button(
                "Sample workspace",
                data=portable_workspace,
                file_name="footy-scout-sample-workspace.json",
                mime="application/json",
                on_click="ignore",
                key="download_workspace",
                width="stretch",
            )

st.caption(
    "Real season data via API-Football · educational estimates only"
    if is_real
    else "100% fictional sample data · educational estimates only"
)
