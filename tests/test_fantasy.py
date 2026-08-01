import math
import unittest

from demo_data import all_demo_players
from fantasy import (
    CAPTAIN_MULTIPLIER,
    DEFAULT_BUDGET_MILLIONS,
    DEFAULT_SQUAD_SIZE,
    MAX_SQUAD_SIZE,
    calculate_player_price,
    calculate_squad,
    player_identity,
    score_player,
    validate_squad,
)


def player(player_id: str, position: str = "Attacker", **stats):
    return {
        "player_id": player_id,
        "name": f"Player {player_id}",
        "position": position,
        "games": 2,
        "minutes": 150,
        "goals": 0,
        "assists": 0,
        "clean_sheets": 0,
        "saves": 0,
        "conceded": 0,
        "rating": 6.5,
        **stats,
    }


class PlayerScoringTests(unittest.TestCase):
    def test_attacker_scoring_uses_minute_goal_assist_card_and_rating_rules(self):
        result = score_player(
            player(
                "a",
                goals=2,
                assists=1,
                clean_sheets=5,
                saves=12,
                conceded=6,
                yellow_cards=1,
                red_cards=1,
                rating=7.6,
            )
        )

        self.assertEqual(result["position"], "Attacker")
        self.assertEqual(
            result["breakdown"],
            {
                "appearances": 4,
                "goals": 8,
                "assists": 3,
                "clean_sheets": 0,
                "saves": 0,
                "conceded": 0,
                "yellow_cards": -1,
                "red_cards": -3,
                "rating_bonus": 8,
            },
        )
        self.assertEqual(result["base_points"], 19)

    def test_goals_and_clean_sheets_are_position_aware(self):
        defender = score_player(
            player(
                "d",
                "Centre-back",
                goals=2,
                clean_sheets=5,
                conceded=6,
            )
        )
        midfielder = score_player(
            player("m", "Midfielder", goals=2, clean_sheets=5, conceded=6)
        )
        attacker = score_player(
            player("f", "Forward", goals=2, clean_sheets=5, conceded=6)
        )

        self.assertEqual(defender["breakdown"]["goals"], 12)
        self.assertEqual(defender["breakdown"]["clean_sheets"], 20)
        self.assertEqual(defender["breakdown"]["conceded"], -3)
        self.assertEqual(midfielder["breakdown"]["goals"], 10)
        self.assertEqual(midfielder["breakdown"]["clean_sheets"], 5)
        self.assertEqual(midfielder["breakdown"]["conceded"], 0)
        self.assertEqual(attacker["breakdown"]["goals"], 8)
        self.assertEqual(attacker["breakdown"]["clean_sheets"], 0)

    def test_goalkeeper_gets_saves_and_conceded_adjustment(self):
        result = score_player(
            player(
                "g",
                "GK",
                clean_sheets=1,
                saves=10,
                conceded=5,
                rating=8.2,
            )
        )

        self.assertEqual(result["position"], "Goalkeeper")
        self.assertEqual(result["breakdown"]["saves"], 3)
        self.assertEqual(result["breakdown"]["clean_sheets"], 4)
        self.assertEqual(result["breakdown"]["conceded"], -2)
        self.assertEqual(result["breakdown"]["rating_bonus"], 12)

    def test_minutes_infer_appearances_when_game_count_is_missing(self):
        result = score_player({"name": "No Games", "minutes": 180})

        self.assertEqual(result["inputs"]["games"], 2)
        self.assertEqual(result["breakdown"]["appearances"], 4)

    def test_malformed_primary_stat_can_fall_back_to_provider_alias(self):
        result = score_player(
            {"name": "Alias", "games": "bad", "appearances": 3, "minutes": 190}
        )

        self.assertEqual(result["inputs"]["games"], 3)
        self.assertEqual(result["breakdown"]["appearances"], 6)

    def test_malformed_and_extreme_stats_are_safe_and_bounded(self):
        result = score_player(
            {
                "player_id": "bad",
                "position": None,
                "games": math.inf,
                "minutes": "not-a-number",
                "goals": -50,
                "assists": 10**100,
                "yellow": math.nan,
                "red": True,
                "rating": "8.5",
            }
        )

        self.assertEqual(result["position"], "Unknown")
        self.assertEqual(result["inputs"]["games"], 0)
        self.assertEqual(result["breakdown"]["goals"], 0)
        self.assertEqual(result["breakdown"]["assists"], 300)
        self.assertEqual(result["breakdown"]["rating_bonus"], 12)
        self.assertTrue(math.isfinite(result["base_points"]))


class PlayerPriceTests(unittest.TestCase):
    def test_provided_blended_value_has_deterministic_compressed_price(self):
        first = calculate_player_price(player("a"), blended_value=100)
        second = calculate_player_price(player("a"), blended_value="100")

        self.assertEqual(first, second)
        self.assertEqual(first["price"], 16.5)
        self.assertEqual(first["blended_value"], 100.0)
        self.assertEqual(first["source"], "provided")

    def test_player_field_can_supply_blended_value(self):
        result = calculate_player_price({"player_id": "a", "blended_valuation": 36})

        self.assertEqual(result["price"], 11.5)
        self.assertEqual(result["source"], "provided")

    def test_missing_provided_value_uses_existing_valuation_methods(self):
        result = calculate_player_price(all_demo_players()[0])

        self.assertEqual(result["source"], "valuation_methods")
        self.assertGreater(result["blended_value"], 0)
        self.assertGreaterEqual(result["price"], 4.0)
        self.assertLessEqual(result["price"], 25.0)


class SquadTests(unittest.TestCase):
    def test_squad_rows_preserve_season_for_comparable_display(self):
        candidate = player("a", season="2024")
        result = calculate_squad([candidate], "a", squad_size=1)
        self.assertEqual(result["players"][0]["season"], "2024")

    def setUp(self):
        self.players = [player(str(index), goals=index) for index in range(5)]
        self.values = {item["player_id"]: 25 for item in self.players}

    def test_default_five_player_squad_is_valid_under_100m(self):
        result = calculate_squad(
            self.players,
            "2",
            blended_values=self.values,
        )

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["required_player_count"], DEFAULT_SQUAD_SIZE)
        self.assertEqual(result["budget"], DEFAULT_BUDGET_MILLIONS)
        self.assertEqual(result["total_value"], 51.0)
        self.assertEqual(result["budget_remaining"], 49.0)
        self.assertEqual(len(result["players"]), 5)
        self.assertEqual(sum(row["is_captain"] for row in result["players"]), 1)

    def test_captain_doubles_points_and_summary_exposes_bonus(self):
        result = calculate_squad(
            self.players,
            "4",
            blended_values=self.values,
        )
        captain = next(row for row in result["players"] if row["is_captain"])

        self.assertEqual(captain["multiplier"], CAPTAIN_MULTIPLIER)
        self.assertEqual(captain["points"], captain["base_points"] * 2)
        self.assertEqual(result["captain_bonus"], captain["base_points"])
        self.assertEqual(
            result["total_points"], result["base_points"] + result["captain_bonus"]
        )

    def test_squad_size_is_configurable_from_one_through_eight(self):
        one = calculate_squad(
            self.players[:1], "0", squad_size=1, blended_values=self.values
        )
        eight_players = [player(str(index)) for index in range(MAX_SQUAD_SIZE)]
        eight = calculate_squad(
            eight_players,
            "0",
            squad_size=MAX_SQUAD_SIZE,
            blended_values={item["player_id"]: 0 for item in eight_players},
        )

        self.assertTrue(one["is_valid"])
        self.assertTrue(eight["is_valid"])
        self.assertEqual(eight["total_value"], 32.0)

    def test_invalid_squad_sizes_are_rejected_without_crashing(self):
        for bad_size in (0, 9, 1.5, True, "not-a-number"):
            with self.subTest(squad_size=bad_size):
                result = validate_squad(
                    self.players,
                    "0",
                    squad_size=bad_size,
                    blended_values=self.values,
                )
                self.assertFalse(result["is_valid"])
                self.assertTrue(
                    any("between 1 and 8" in error for error in result["errors"])
                )

    def test_duplicate_players_and_missing_identity_are_rejected(self):
        duplicate = validate_squad(
            [self.players[0], self.players[0]],
            "0",
            squad_size=2,
            blended_values=self.values,
        )
        missing_identity = validate_squad(
            [{"games": 1}],
            None,
            squad_size=1,
        )

        self.assertIn("A player can only appear once in a squad.", duplicate["errors"])
        self.assertIn(
            "Every player needs a stable ID or name.", missing_identity["errors"]
        )

    def test_captain_is_required_and_must_belong_to_squad(self):
        missing = validate_squad(self.players, None, blended_values=self.values)
        outsider = validate_squad(self.players, "outside", blended_values=self.values)

        self.assertIn("Choose one captain.", missing["errors"])
        self.assertIn(
            "The captain must be one of the selected players.", outsider["errors"]
        )

    def test_over_budget_squad_returns_clear_amount(self):
        result = validate_squad(
            self.players,
            "0",
            budget=100,
            blended_values={item["player_id"]: 250 for item in self.players},
        )

        self.assertFalse(result["is_valid"])
        self.assertEqual(result["total_value"], 119.0)
        self.assertEqual(result["budget_remaining"], -19.0)
        self.assertIn("Squad is €19.0M over the budget.", result["errors"])

    def test_invalid_budget_and_malformed_player_input_return_errors(self):
        bad_budget = validate_squad(
            self.players, "0", budget=-5, blended_values=self.values
        )
        bad_players = calculate_squad("not a squad", None)

        self.assertIn("Budget must be a positive number.", bad_budget["errors"])
        self.assertFalse(bad_players["is_valid"])
        self.assertIn("Players must be supplied as a sequence.", bad_players["errors"])

    def test_identity_supports_api_ids_and_name_fallback(self):
        self.assertEqual(player_identity({"api_id": 123, "name": "A"}), "123")
        self.assertEqual(
            player_identity({"name": "  Alex  Doe ", "team": " FC One "}),
            "name:alex doe|team:fc one",
        )
        self.assertIsNone(player_identity("not a player"))

    def test_blended_value_mapping_accepts_name_keys_for_ui_integration(self):
        named = player("x")
        result = calculate_squad(
            [named],
            "x",
            squad_size=1,
            blended_values={named["name"]: 64},
        )

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["players"][0]["price"], 14.0)
        self.assertEqual(result["players"][0]["price_source"], "provided")


if __name__ == "__main__":
    unittest.main()
