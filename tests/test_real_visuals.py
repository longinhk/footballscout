import unittest
from copy import deepcopy

from ui_components import APP_CSS, comparison_profile_html


def real_attacker(
    name: str,
    *,
    minutes: int = 900,
    goals: int = 12,
    assists: int = 6,
    pass_accuracy: float | None = 86.4,
) -> dict:
    return {
        "player_id": f"api-{name}",
        "name": name,
        "position": "Attacker",
        "season": "2025",
        "minutes": minutes,
        "rating": 7.82,
        "goals": goals,
        "assists": assists,
        "shots": 52,
        "key_passes": 31,
        "pass_accuracy": pass_accuracy,
        "tackles": 7,
        "interceptions": 3,
        "duels_won_pct": 54.2,
        "data_source": "api_football",
    }


class RealComparisonProfileTests(unittest.TestCase):
    def test_real_players_render_paired_values_without_cohort_claims(self):
        players = [
            real_attacker("Lionel <Messi>"),
            real_attacker("Harry Kane", minutes=720, goals=8),
        ]

        result = comparison_profile_html(players)

        self.assertIn('aria-label="Paired season metric profile"', result)
        self.assertIn("Lionel &lt;Messi&gt;", result)
        self.assertIn("Goals / 90", result)
        self.assertIn("1.20", result)
        self.assertIn("1.00", result)
        self.assertIn("does not rank either player", result)
        self.assertNotIn("fictional", result.casefold())
        self.assertNotIn("<script", result.casefold())
        self.assertNotIn("<img", result.casefold())

    def test_missing_value_is_labeled_unavailable_not_changed_to_zero(self):
        players = [
            real_attacker("Player One", pass_accuracy=None),
            real_attacker("Player Two", pass_accuracy=84.2),
        ]

        result = comparison_profile_html(players)

        self.assertIn(
            "Pass accuracy. Player A, Player One: unavailable. "
            "Player B, Player Two: 84.2%. Percentage",
            result,
        )
        self.assertIn("Not available", result)
        self.assertIn("84.2%", result)
        self.assertIn("fs-pair-track is-unavailable", result)

    def test_recorded_zero_remains_a_zero_and_keeps_the_metric(self):
        players = [
            real_attacker("Player One", goals=0),
            real_attacker("Player Two", goals=0),
        ]

        result = comparison_profile_html(players)

        self.assertIn(
            "Goals / 90. Player A, Player One: 0.00. "
            "Player B, Player Two: 0.00. Per 90 minutes",
            result,
        )

    def test_goalkeeper_profile_uses_goalkeeper_signals_and_direction_note(self):
        players = [
            {
                "name": "Keeper One",
                "position": "Goalkeeper",
                "season": "2025",
                "minutes": 900,
                "rating": 7.1,
                "saves": 42,
                "conceded": 8,
                "clean_sheets": None,
                "pass_accuracy": 78.0,
                "duels_won_pct": None,
            },
            {
                "name": "Keeper Two",
                "position": "Goalkeeper",
                "season": "2025",
                "minutes": 900,
                "rating": 7.3,
                "saves": 37,
                "conceded": 6,
                "clean_sheets": 5,
                "pass_accuracy": 82.0,
                "duels_won_pct": None,
            },
        ]

        result = comparison_profile_html(players)

        self.assertIn("Saves / 90", result)
        self.assertIn("Goals conceded / 90", result)
        self.assertIn("Lower is better", result)
        self.assertIn(
            "Clean sheets. Player A, Keeper One: unavailable. "
            "Player B, Keeper Two: 5. Season total",
            result,
        )

    def test_empty_profile_has_an_honest_fallback(self):
        players = [
            {"name": "No Data A", "position": "Unknown", "season": "2025"},
            {"name": "No Data B", "position": "Unknown", "season": "2025"},
        ]

        result = comparison_profile_html(players)

        self.assertIn("No comparable season metrics were returned", result)
        self.assertNotIn("Season rating", result)

    def test_chart_is_source_agnostic(self):
        players = [real_attacker("Player One"), real_attacker("Player Two")]
        other_source = deepcopy(players)
        for player in other_source:
            player["data_source"] = "another_provider"

        self.assertEqual(
            comparison_profile_html(players),
            comparison_profile_html(other_source),
        )

    def test_requires_exactly_two_players(self):
        with self.assertRaisesRegex(ValueError, "exactly two players"):
            comparison_profile_html([real_attacker("Only Player")])

    def test_responsive_and_missing_data_styles_are_present(self):
        self.assertIn(".fs-pair-profile-head", APP_CSS)
        self.assertIn("grid-template-columns:minmax(0,1fr) 88px", APP_CSS)
        self.assertIn(".fs-pair-track.is-unavailable", APP_CSS)
        self.assertIn("@media (max-width: 640px)", APP_CSS)


if __name__ == "__main__":
    unittest.main()
