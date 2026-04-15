import requests
import pandas as pd
import streamlit as st
import time
import requests

# Use Streamlit secrets in production, or python-dotenv for local dev
def get_api_key():
    try:
        return st.secrets["RAPIDAPI_KEY"]
    except:
        # use your own key
        import os
        return os.getenv("RAPIDAPI_KEY", "YOUR_RAPIDAPI_KEY")

def fetch_player_stats(player_id, season="2024"):
    """
    Fetch player statistics from API-Football.
    Returns a dictionary with name, age, games, goals, assists, contract_years.
    """
    url = "https://v3.football.api-sports.io"
    querystring = {"id": str(player_id), "season": str(season)}
    
   try:
    api_key = st.secrets["RAPIDAPI_KEY"]
    except:
    st.error("please set Streamlit Secrets  RAPIDAPI_KEY！")
    return None

headers = {
    "x-apisports-key": api_key
}
try:                          
    response = requests.get(url, headers=headers, params=querystring, timeout=10)
    response.raise_for_status()
    data = response.json()
except requests.exceptions.RequestException as e:
    st.error(f"API request failed: {e}")
    return None
    # Parse the response
    if not data.get("response"):
        st.warning("No data found for this player ID. Please check the ID.")
        return None

    try:
        player_info = data['response'][0]['player']
        stats = data['response'][0]['statistics'][0]

        # Basic stats
        games = stats['games'].get('appearences', 0) or 0
        goals = stats['goals'].get('total', 0) or 0
        assists = stats['goals'].get('assists', 0) or 0
        age = player_info.get('age', 0)

        # Contract years – not provided by this API, so we use a placeholder.
        # You could enhance this by calling another endpoint or allowing manual input.
        contract_years = 3  # default assumption

        return {
            'name': player_info.get('name', 'Unknown'),
            'age': age,
            'games': games,
            'goals': goals,
            'assists': assists,
            'contract_years': contract_years
        }
    except (KeyError, IndexError, TypeError) as e:
        st.error(f"Error parsing player data: {e}")
        return None

def fetch_data(url):
    for i in range(3): 
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}, retrying in {2**i} seconds...")
            time.sleep(2**i)
    return None
