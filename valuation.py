import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
import joblib  # for saving/loading model
import os

# ---------- Position‑Based Heuristic Formulas ----------
def calculate_value_heuristic(stats):
    """
    stats: dict from data_fetcher
    Returns estimated value in million euros.
    """
    position = stats.get('position', 'Unknown').lower()
    age = stats.get('age', 1)
    contract = stats.get('contract_years', 1)

    # Base value multiplier
    base = 10

    if 'goalkeeper' in position:
        # Use saves, clean sheets, conceded
        saves = stats.get('saves', 0)
        clean = stats.get('clean_sheets', 0)
        conceded = stats.get('conceded', 1) or 1  # avoid division by zero
        performance = (saves * 0.4 + clean * 0.6) / conceded
    elif 'defender' in position:
        tackles = stats.get('tackles', 0)
        interceptions = stats.get('interceptions', 0)
        clean = stats.get('clean_sheets', 0)
        performance = (tackles * 0.3 + interceptions * 0.3 + clean * 0.4)
    elif 'midfielder' in position:
        goals = stats.get('goals', 0)
        assists = stats.get('assists', 0)
        tackles = stats.get('tackles', 0)
        performance = (goals * 0.4 + assists * 0.4 + tackles * 0.2)
    else:  # attacker / forward
        goals = stats.get('goals', 0)
        assists = stats.get('assists', 0)
        performance = (goals * 0.6 + assists * 0.4)

    value = (performance / age) * contract * base
    return round(value, 2)

# ---------- Machine Learning Model (Trained on Historical Data) ----------
MODEL_FILE = "transfer_model.pkl"

def train_model(csv_path="transfer_data.csv"):
    """
    Train a linear regression model on historical transfer data.
    Expected CSV columns: age, goals, assists, tackles, clean_sheets, saves, conceded, position_encoded, transfer_fee
    (position_encoded: 0=GK,1=DEF,2=MID,3=FWD)
    """
    if not os.path.exists(csv_path):
        # Create a dummy dataset if none exists (for demonstration)
        data = {
            'age': [25, 28, 22, 30, 26],
            'goals': [20, 5, 15, 2, 10],
            'assists': [10, 8, 12, 1, 5],
            'tackles': [5, 30, 15, 40, 10],
            'clean_sheets': [0, 10, 0, 15, 0],
            'saves': [0, 0, 0, 0, 50],
            'conceded': [30, 20, 25, 15, 10],
            'position_encoded': [3, 1, 2, 0, 0],  # FWD, DEF, MID, GK, GK
            'transfer_fee': [80, 40, 60, 25, 30]  # million €
        }
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)
    else:
        df = pd.read_csv(csv_path)

    # Features and target
    features = ['age', 'goals', 'assists', 'tackles', 'clean_sheets', 'saves', 'conceded', 'position_encoded']
    X = df[features]
    y = df['transfer_fee']

    # Train
    model = LinearRegression()
    model.fit(X, y)

    # Save model
    joblib.dump(model, MODEL_FILE)
    return model

def load_model():
    """Load trained model or train if not exists."""
    if os.path.exists(MODEL_FILE):
        return joblib.load(MODEL_FILE)
    else:
        return train_model()

def predict_value_ml(stats):
    """
    Use trained ML model to predict transfer value.
    stats: dict from data_fetcher
    """
    model = load_model()

    # Encode position
    pos = stats.get('position', '').lower()
    if 'goalkeeper' in pos:
        pos_enc = 0
    elif 'defender' in pos:
        pos_enc = 1
    elif 'midfielder' in pos:
        pos_enc = 2
    else:
        pos_enc = 3

    # Prepare feature vector (order must match training)
    features = [[
        stats.get('age', 25),
        stats.get('goals', 0),
        stats.get('assists', 0),
        stats.get('tackles', 0),
        stats.get('clean_sheets', 0),
        stats.get('saves', 0),
        stats.get('conceded', 1),
        pos_enc
    ]]

    pred = model.predict(features)[0]
    return round(pred, 2)

def compare_methods(stats):
    heuristic = calculate_value_heuristic(stats)
    ml = predict_value_ml(stats)
    return {'heuristic': heuristic, 'ml': ml}
