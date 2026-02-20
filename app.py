import streamlit as st
from data_fetcher import fetch_player_stats
from valuation import calculate_value_heuristic, predict_value_ml, compare_methods
from pdf_report import generate_valuation_pdf

st.set_page_config(page_title="Footy-Scout Pro", page_icon="⚽", layout="centered")
st.title("⚽ Footy-Scout Pro: Position‑Aware Player Valuation")
st.markdown("Compare players using position‑specific metrics and machine learning.")

with st.sidebar:
    st.header("Player IDs")
    player1_id = st.number_input("Player 1 ID", min_value=1, value=282, step=1)
    player2_id = st.number_input("Player 2 ID", min_value=1, value=874, step=1)
    season = st.text_input("Season", value="2024")
    method = st.radio("Valuation Method", ["Heuristic", "ML Model", "Both"])
    compare_btn = st.button("Compare Players")

if compare_btn:
    with st.spinner("Fetching player data..."):
        p1 = fetch_player_stats(player1_id, season)
        p2 = fetch_player_stats(player2_id, season)

    if p1 and p2:
        col1, col2 = st.columns(2)

        def display_player(player, col):
            with col:
                st.subheader(player['name'])
                st.write(f"**Position:** {player['position']}")
                st.write(f"**Age:** {player['age']}")
                st.write(f"**Games:** {player['games']}")
                st.write(f"**Goals:** {player['goals']}  |  **Assists:** {player['assists']}")
                st.write(f"**Tackles:** {player['tackles']}  |  **Clean Sheets:** {player['clean_sheets']}")
                if 'saves' in player:
                    st.write(f"**Saves:** {player['saves']}  |  **Conceded:** {player['conceded']}")

                if method == "Heuristic":
                    val = calculate_value_heuristic(player)
                    st.metric("Heuristic Value (€M)", val)
                elif method == "ML Model":
                    val = predict_value_ml(player)
                    st.metric("ML Predicted Value (€M)", val)
                else:  # Both
                    h = calculate_value_heuristic(player)
                    m = predict_value_ml(player)
                    st.metric("Heuristic", h)
                    st.metric("ML Model", m)
                return val if method != "Both" else (h, m)

        val1 = display_player(p1, col1)
        val2 = display_player(p2, col2)

        # Comparison summary
        if method != "Both":
            if val1 > val2:
                st.success(f"✅ **{p1['name']}** is more valuable (€{val1}M vs €{val2}M)")
            elif val2 > val1:
                st.success(f"✅ **{p2['name']}** is more valuable (€{val2}M vs €{val1}M)")
            else:
                st.info("Equal estimated value.")
        else:
            # For both, just show heuristic comparison (or you could average)
            h1, m1 = val1
            h2, m2 = val2
            st.write("**Heuristic comparison:**")
            if h1 > h2:
                st.write(f"✅ {p1['name']} (€{h1}M vs €{h2}M)")
            else:
                st.write(f"✅ {p2['name']} (€{h2}M vs €{h1}M)")
            st.write("**ML comparison:**")
            if m1 > m2:
                st.write(f"✅ {p1['name']} (€{m1}M vs €{m2}M)")
            else:
                st.write(f"✅ {p2['name']} (€{m2}M vs €{m1}M)")

        # PDF download (optional – you can extend to include both values)
        pdf_path = generate_valuation_pdf(p1, p2, [val1, val2] if method!="Both" else [h1, h2])
        with open(pdf_path, "rb") as f:
            st.download_button("📄 Download PDF Report", f, "valuation_report.pdf")
    else:
        st.error("Could not retrieve data for one or both players.")
