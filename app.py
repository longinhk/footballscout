"""Footy-Scout Streamlit application."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from data_fetcher import FootballAPIError, fetch_player_stats, get_api_key
from demo_data import demo_player_names, get_demo_player
from pdf_report import generate_valuation_pdf
from ui_components import (
    APP_CSS,
    included_items,
    insights_html,
    masthead_html,
    matchup_html,
    overview_html,
    performance_duel_html,
    player_key_html,
    section_header_html,
    sidebar_brand_html,
    sidebar_step_html,
    valuation_lab_html,
)
from valuation import compare_methods, per_90


st.set_page_config(
    page_title="Footy-Scout",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)
st.html(APP_CSS)


@st.cache_data(ttl=900, show_spinner=False)
def cached_player(player_id: int, season: str, _api_key: str) -> dict[str, Any]:
    """Cache public season data without hashing or retaining the API secret."""
    return fetch_player_stats(player_id, season, _api_key)


@st.cache_data(show_spinner=False)
def cached_pdf(
    players: list[dict[str, Any]], valuations: list[dict[str, float]]
) -> bytes:
    """Create a report once for an unchanged comparison."""
    return generate_valuation_pdf(players, valuations)


def blended_value(values: dict[str, float]) -> float:
    """Return the documented equal-weight average of all valuation methods."""
    return sum(values.values()) / len(values)


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
    """Build a complete, analysis-friendly CSV representation."""
    rows = []
    for player, values, blended in zip(players, valuations, blended_values):
        rows.append(
            {
                "Player": player.get("name"),
                "Team(s)": included_items(player, "teams", "team"),
                "Competition(s)": included_items(player, "competitions", "league"),
                "Season": player.get("season"),
                "Position": player.get("position"),
                "Age": player.get("age"),
                "Appearances": player.get("games"),
                "Minutes": player.get("minutes"),
                "Rating": player.get("rating"),
                "Goals": player.get("goals"),
                "Goals per 90": per_90(player.get("goals"), player.get("minutes")),
                "Assists": player.get("assists"),
                "Assists per 90": per_90(player.get("assists"), player.get("minutes")),
                "Tackles per 90": per_90(player.get("tackles"), player.get("minutes")),
                "Interceptions per 90": per_90(
                    player.get("interceptions"), player.get("minutes")
                ),
                "Saves per 90": per_90(player.get("saves"), player.get("minutes")),
                "Clean sheets": player.get("clean_sheets"),
                "Heuristic (EUR M)": values["Heuristic"],
                "Demo ML (EUR M)": values["Demo ML"],
                "Blended (EUR M)": blended,
            }
        )
    return pd.DataFrame(rows)


def render_methodology() -> None:
    """Explain the deliberately limited educational valuation models."""
    with st.expander("Methodology & limitations"):
        st.markdown(
            """
            - **Heuristic** uses bounded, position-aware per-90 output, age and availability.
            - **Demo ML** is a constrained model trained on a small synthetic sample. It is a product demonstration, not a market model.
            - **Blended estimate** gives the two methods equal weight. Their spread shows disagreement, not a confidence interval.

            Contract length, club finances, injury history, league strength and real transfer comparables are not included. Treat every value as an educational signal, never an official valuation.
            """
        )


def render_demo_setup() -> tuple[list[dict[str, Any]], str]:
    """Render the frictionless fictional-player picker."""
    names = demo_player_names()
    st.html(sidebar_step_html(2, "Build the matchup", "Pick any two players"))

    first_name = st.selectbox(
        "Player A",
        names,
        index=0,
        key="demo_player_a",
        width="stretch",
    )
    second_name = st.selectbox(
        "Player B",
        names,
        index=1,
        key="demo_player_b",
        width="stretch",
    )
    st.html(player_key_html())

    if first_name == second_name:
        st.error("Choose two different players. Keeping the last valid matchup.")
    else:
        st.session_state["demo_result_names"] = (first_name, second_name)

    result_names = st.session_state.get("demo_result_names", (names[0], names[1]))
    if result_names[0] == result_names[1]:
        result_names = (names[0], names[1])

    st.html(sidebar_step_html(3, "Read the report", "The dashboard updates live"))
    st.caption("Fictional sample data · no credentials needed")
    return [get_demo_player(name) for name in result_names], "Demo data · 2025"


def render_live_setup(configured_key: str) -> tuple[list[dict[str, Any]] | None, str]:
    """Render live API setup and keep the last successful result available."""
    if configured_key:
        st.badge("Server API key ready", color="green")
    else:
        st.badge("API key needed", color="gray")

    st.html(sidebar_step_html(2, "Build the matchup", "Use API-Football player IDs"))
    with st.form("live_comparison_form"):
        season = st.number_input(
            "Season start year",
            min_value=2000,
            max_value=date.today().year,
            value=date.today().year - 1,
            key="live_season",
        )
        player1_id = st.number_input(
            "Player A ID",
            min_value=1,
            value=282,
            key="live_player_a_id",
        )
        player2_id = st.number_input(
            "Player B ID",
            min_value=1,
            value=874,
            key="live_player_b_id",
        )
        with st.expander("API connection", expanded=not bool(configured_key)):
            api_key_override = st.text_input(
                "API key override",
                value="",
                type="password",
                key="api_key_override",
                help=(
                    "Optional when a server key is configured. It is used only for "
                    "this request and is never written to disk."
                ),
            )
        submitted = st.form_submit_button(
            "Run live comparison",
            type="primary",
            width="stretch",
        )

    st.html(player_key_html())
    st.caption("Competition rows returned by the API are combined.")

    if submitted:
        if player1_id == player2_id:
            st.error("Choose two different player IDs.")
        else:
            api_key = api_key_override.strip() or configured_key
            if not api_key:
                st.error("Enter an API-Football key to run this comparison.")
            else:
                try:
                    with st.spinner(f"Fetching the {season} season…"):
                        live_players = [
                            cached_player(int(player1_id), str(season), api_key),
                            cached_player(int(player2_id), str(season), api_key),
                        ]
                    st.session_state["live_result"] = {
                        "players": live_players,
                        "season": str(season),
                    }
                except FootballAPIError as exc:
                    st.error(str(exc))
                    if st.session_state.get("live_result"):
                        st.warning("Keeping the last successful live comparison.")

    st.html(sidebar_step_html(3, "Read the report", "Results stay until replaced"))
    saved_result = st.session_state.get("live_result")
    if not saved_result:
        return None, "Live API · awaiting matchup"
    return (
        saved_result["players"],
        f"API-Football · {saved_result['season']}",
    )


configured_key = get_api_key()
players: list[dict[str, Any]] | None

with st.sidebar:
    st.html(sidebar_brand_html())
    st.html(sidebar_step_html(1, "Choose the source", "Explore or connect live data"))
    source = st.segmented_control(
        "Data source",
        ("Demo data", "Live API"),
        default="Demo data",
        key="source_mode",
        label_visibility="collapsed",
        width="stretch",
    )
    if source == "Live API":
        players, source_note = render_live_setup(configured_key)
    else:
        players, source_note = render_demo_setup()

st.html(masthead_html(source_note))
st.title("Compare the season. See the edge.")
st.html(
    """
    <p class="fs-deck">
      Put two players on the same canvas. Read their output, role signals and
      transparent valuation estimates without digging through disconnected tables.
    </p>
    """
)

if players is None:
    st.info(
        "Set up a live comparison in the sidebar, or switch to Demo data to explore "
        "the complete experience immediately."
    )
    render_methodology()
    st.stop()

valuations = [compare_methods(player) for player in players]
blended_values = [blended_value(values) for values in valuations]

st.html(matchup_html(players, valuations, blended_values))

st.html(
    section_header_html(
        "Season overview",
        "The essentials, aligned",
        "Availability and form in one glance",
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

st.html(
    section_header_html(
        "Performance duel",
        "Output in context",
        "Per-90 rates normalize playing time",
    )
)
st.html(performance_duel_html(players))

st.html(
    section_header_html(
        "Valuation lab",
        "Two methods, one clear comparison",
        "Educational models · equal-weight blend",
    )
)
st.html(valuation_lab_html(players, valuations))
render_methodology()

comparison_export = export_frame(players, valuations, blended_values)
stem = _report_stem(players)
with st.container(key="export_tray"):
    intro, pdf_column, csv_column = st.columns(
        [1.65, 1, 1], gap="medium", vertical_alignment="center"
    )
    with intro:
        st.subheader("Take the report with you")
        st.caption("A polished PDF for sharing, or structured CSV for deeper work.")
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

st.caption(
    "Educational estimates only · not financial advice or official market values"
)
