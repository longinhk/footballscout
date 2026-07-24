"""FootballScout — player comparison and transparent ML valuation demo."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_fetcher import FootballAPIError, FootballClient, PlayerOption, get_secret
from explanations import llm_explanation
from pdf_report import generate_valuation_pdf
from valuation import ValuationResult, evaluate_demo_model, feature_comparison, predict_value

st.set_page_config(page_title="FootballScout", page_icon="⚽", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1200px; padding-top: 1.8rem;}
      .hero {padding: 1.4rem 1.6rem; border-radius: 18px;
             background: linear-gradient(120deg,#081c15,#1b4332); color: white;}
      .hero h1 {margin: 0; font-size: 2.4rem;}
      .hero p {color: #b7e4c7; margin-bottom: 0;}
      [data-testid="stMetric"] {background:#f8fafc; border:1px solid #e2e8f0;
                               border-radius:12px; padding:12px;}
    </style>
    <div class="hero">
      <h1>⚽ FootballScout</h1>
      <p>Live performance comparison with transparent machine-learning estimates.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def cached_search(query: str, api_key: str) -> list[PlayerOption]:
    return FootballClient(api_key).search_players(query)


@st.cache_data(ttl=900, show_spinner=False, max_entries=200)
def cached_stats(player_id: int, season: int, api_key: str) -> dict:
    return FootballClient(api_key).player_stats(player_id, season)


def search_box(slot: int, api_key: str) -> PlayerOption | None:
    query = st.text_input(
        f"Player {slot}",
        key=f"query_{slot}",
        placeholder="Type at least 3 letters, e.g. Messi",
    )
    if len(query.strip()) < 3:
        st.caption("Enter at least three characters.")
        return None
    try:
        options = cached_search(query.strip(), api_key)
    except FootballAPIError as exc:
        st.error(str(exc))
        return None
    if not options:
        st.warning("No matching players.")
        return None
    return st.selectbox(
        f"Select player {slot}",
        options,
        format_func=lambda option: option.label,
        key=f"player_{slot}",
    )


def player_summary(player: dict, result: ValuationResult) -> None:
    title, portrait = st.columns([5, 1])
    title.subheader(player["name"])
    title.caption(
        f"{player['team']} · {player['league']} · {player['position']} · {player['nationality']}"
    )
    if player.get("photo"):
        portrait.image(player["photo"], width=78)
    columns = st.columns(4)
    for column, label, value in zip(
        columns,
        ["Age", "Appearances", "Rating", "ML estimate"],
        [player["age"], player["appearances"], player["rating"] or "—", f"€{result.value_millions:.2f}M"],
    ):
        column.metric(label, value)
    st.dataframe(
        pd.DataFrame(
            {
                "Metric": ["Minutes", "Goals", "Assists", "Key passes", "Tackles", "Interceptions"],
                "Value": [
                    player["minutes"],
                    player["goals"],
                    player["assists"],
                    player["key_passes"],
                    player["tackles"],
                    player["interceptions"],
                ],
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def radar_chart(first: dict, second: dict) -> go.Figure:
    evidence = feature_comparison(first, second)
    labels = [item["metric"] for item in evidence]
    labels_closed = labels + [labels[0]]
    figure = go.Figure()
    for player, key, color in [
        (first, "first_normalized", "#2d6a4f"),
        (second, "second_normalized", "#f59e0b"),
    ]:
        values = [item[key] for item in evidence]
        figure.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=labels_closed,
                fill="toself",
                name=player["name"],
                line_color=color,
                opacity=0.72,
            )
        )
    figure.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100]}},
        margin={"l": 35, "r": 35, "t": 30, "b": 30},
        height=440,
        legend={"orientation": "h"},
    )
    return figure


with st.sidebar:
    st.header("Configuration")
    default_key = get_secret("API_SPORTS_KEY") or get_secret("RAPIDAPI_KEY") or ""
    api_key = st.text_input(
        "API-Sports key",
        value=default_key,
        type="password",
        help="Direct key from dashboard.api-football.com. The field is not persisted.",
    ).strip()
    season = st.number_input(
        "Season start year",
        min_value=2010,
        max_value=date.today().year,
        value=date.today().year - 1,
    )
    enable_llm = st.toggle("Use optional AI explanation", value=False)
    if enable_llm:
        openai_key = st.text_input(
            "OpenAI API key",
            value=get_secret("OPENAI_API_KEY") or "",
            type="password",
        ).strip()
    else:
        openai_key = ""
    st.divider()
    metrics = evaluate_demo_model()
    st.caption("Bundled regression baseline")
    st.metric("Synthetic holdout MAE", f"€{metrics['mae_millions']:.2f}M")
    st.caption(f"R² {metrics['r2']} · {metrics['test_rows']} test rows")

st.markdown("### Find two players")
if not api_key:
    st.info("Enter your direct API-Sports key in the sidebar to begin.")
    st.stop()

search_left, search_right = st.columns(2, gap="large")
with search_left:
    first_option = search_box(1, api_key)
with search_right:
    second_option = search_box(2, api_key)

compare = st.button(
    "Compare selected players",
    type="primary",
    disabled=not first_option or not second_option,
    use_container_width=True,
)
if not compare:
    st.caption("Search results and statistics are cached to protect the 100-request daily allowance.")
    st.stop()
if first_option.id == second_option.id:
    st.error("Choose two different players.")
    st.stop()

try:
    with st.spinner("Fetching season statistics…"):
        players = [
            cached_stats(first_option.id, int(season), api_key),
            cached_stats(second_option.id, int(season), api_key),
        ]
except FootballAPIError as exc:
    st.error(str(exc))
    st.stop()

results = [predict_value(player) for player in players]
st.divider()
left, right = st.columns(2, gap="large")
with left:
    player_summary(players[0], results[0])
with right:
    player_summary(players[1], results[1])

st.markdown("### Performance profile")
st.plotly_chart(radar_chart(players[0], players[1]), use_container_width=True)
st.caption("Each radar axis is normalized to the stronger of the two selected players; it is comparative, not absolute.")

explanation = llm_explanation(
    players[0], players[1], results[0], results[1], openai_key if enable_llm else None
)
st.markdown("### Why the estimates differ")
st.write(explanation)
st.warning(results[0].caveat, icon="⚠️")

summary = pd.DataFrame(
    [
        {
            "Player": player["name"],
            "Position": player["position"],
            "Age": player["age"],
            "Rating": player["rating"],
            "Estimate (€M)": result.value_millions,
        }
        for player, result in zip(players, results)
    ]
)
st.dataframe(summary, hide_index=True, use_container_width=True)
st.download_button(
    "Download comparison PDF",
    generate_valuation_pdf(players, results, explanation),
    "footballscout_comparison.pdf",
    "application/pdf",
)
