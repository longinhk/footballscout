import unittest

from app_state import (
    claim_real_search,
    initialize_session_state,
    preserve_selected_pool,
    seed_fantasy_from_comparison,
)


class SessionInitializationTests(unittest.TestCase):
    def test_defaults_preserve_existing_state(self):
        state = {"workspace_mode": "Fantasy challenge"}

        initialize_session_state(
            state,
            default_pair=("a", "b"),
            age_bounds=(18, 40),
            default_squad_size=4,
        )

        self.assertEqual(state["workspace_mode"], "Fantasy challenge")
        self.assertEqual(state["offline_player_a"], "a")
        self.assertEqual(state["fantasy_squad_size"], 4)


class SearchGuardTests(unittest.TestCase):
    def test_search_guard_uses_per_player_cooldowns_and_a_shared_budget(self):
        state = {}

        self.assertIsNone(claim_real_search(state, "A", now=100))
        self.assertIsNotNone(claim_real_search(state, "A", now=101))
        self.assertIsNone(claim_real_search(state, "B", now=101))
        self.assertEqual(state["real_search_count"], 2)

    def test_search_guard_stops_at_the_session_limit(self):
        state = {"real_search_count": 2}

        message = claim_real_search(state, "A", now=100, maximum_searches=2)

        self.assertIn("session", message.casefold())


class FantasyStateTests(unittest.TestCase):
    def test_filtered_pool_retains_selected_players(self):
        unfiltered = {
            "a": {"player_id": "a", "name": "A"},
            "b": {"player_id": "b", "name": "B"},
        }

        pool, selected, hidden_count = preserve_selected_pool(
            unfiltered,
            [unfiltered["a"]],
            ["b"],
        )

        self.assertEqual(list(pool), ["a", "b"])
        self.assertEqual(selected, ["b"])
        self.assertEqual(hidden_count, 1)

    def test_comparison_seeds_real_fantasy_squad(self):
        players = [
            {"player_id": "api-1", "name": "A", "season": "2024"},
            {"player_id": "api-2", "name": "B", "season": "2024"},
        ]
        state = {"real_favorites": {}}

        seed_fantasy_from_comparison(state, players)

        self.assertEqual(state["workspace_mode"], "Fantasy challenge")
        self.assertEqual(state["fantasy_pool_mode"], "Real favourites")
        self.assertEqual(state["fantasy_selected_ids"], ["api-1", "api-2"])
        self.assertEqual(state["fantasy_favorite_season"], "2024")
        self.assertEqual(state["fantasy_captain"], "api-1")


if __name__ == "__main__":
    unittest.main()
