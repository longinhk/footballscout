import requests
import streamlit as st

@st.cache_data(ttl=3600)
def fetch_player_stats(player_id, season="2024"):
    url = "https://v3.football.api-sports.io/players"
    headers = {
        "x-apisports-key": st.secrets["RAPIDAPI_KEY"]
    }
    params = {
        "id": player_id,
        "season": season
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("response"):
            return None
        
        player_info = data['response'][0]['player']
        stats = data['response'][0]['statistics'][0]
        
        position = stats.get('games', {}).get('position', 'Unknown')
        
        tackles = stats.get('tackles', {}).get('total', 0) or 0
        clean_sheets = stats.get('clean_sheets', 0) or 0
        
        saves = stats.get('goals', {}).get('saves', 0) or 0
        conceded = stats.get('goals', {}).get('conceded', 0) or 0
        
        return {
            'name': player_info.get('name', 'Unknown'),
            'age': player_info.get('age', 0),
            'position': position,
            'games': stats.get('games', {}).get('appearences', 0) or 0,
            'goals': stats.get('goals', {}).get('total', 0) or 0,
            'assists': stats.get('goals', {}).get('assists', 0) or 0,
            'tackles': tackles,
            'clean_sheets': clean_sheets,
            'saves': saves,
            'conceded': conceded
        }
    except Exception as e:
        st.error(f"API 錯誤: {e}")
        return None
