def calculate_value(goals, assists, age, contract_years, base_value=10):
    """
    Simple valuation formula:
    value = (goals*0.5 + assists*0.3) / age * contract_years * base_value
    """
    if age <= 0:
        return 0
    performance = goals * 0.5 + assists * 0.3
    value = (performance / age) * contract_years * base_value
    return round(value, 2)

def compare_players(player1_stats, player2_stats):
    """
    Takes two player stat dictionaries and returns a comparison dict.
    """
    v1 = calculate_value(**player1_stats)
    v2 = calculate_value(**player2_stats)

    return {
        'player1_value': v1,
        'player2_value': v2,
        'better': 'Player 1' if v1 > v2 else 'Player 2' if v2 > v1 else 'Equal'
    }
