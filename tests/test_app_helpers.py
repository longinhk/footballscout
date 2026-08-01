import unittest

from app_helpers import (
    comparison_query,
    filter_player_pool,
    filter_profiles,
    parse_comparison_query,
    parse_real_favorites,
    real_favorites_bytes,
    real_result_session_updates,
    remove_real_favorite,
    save_league_entry,
    save_real_favorite,
    toggle_real_favorite_snapshot,
)


PROFILES = [
    {
        "api_id": 1,
        "player_id": "api-1",
        "name": "A",
        "position": "Attacker",
        "nationality": "Argentina",
        "age": 24,
    },
    {
        "api_id": 2,
        "player_id": "api-2",
        "name": "B",
        "position": "Goalkeeper",
        "nationality": "Spain",
        "age": 34,
    },
]


class ProfileFilterTests(unittest.TestCase):
    def test_filters_are_local_and_composable(self):
        self.assertEqual(
            [
                item["api_id"]
                for item in filter_profiles(PROFILES, positions=["Attacker"])
            ],
            [1],
        )
        self.assertEqual(
            [
                item["api_id"]
                for item in filter_profiles(
                    PROFILES, nationality="arg", age_range=(20, 30)
                )
            ],
            [1],
        )

    def test_unknown_age_is_excluded_only_when_age_filter_is_active(self):
        profiles = [dict(PROFILES[0], age=None)]
        self.assertEqual(len(filter_profiles(profiles)), 1)
        self.assertEqual(filter_profiles(profiles, age_range=(18, 40)), [])

    def test_loaded_pool_filters_club_and_competition_context(self):
        players = [
            dict(
                PROFILES[0],
                teams=["Inter Miami"],
                competitions=["Major League Soccer"],
            ),
            dict(PROFILES[1], team="Madrid FC", league="La Liga"),
        ]

        self.assertEqual(
            [player["api_id"] for player in filter_player_pool(players, club="miami")],
            [1],
        )
        self.assertEqual(
            [
                player["api_id"]
                for player in filter_player_pool(players, competition="liga")
            ],
            [2],
        )


class SharingTests(unittest.TestCase):
    def test_comparison_query_round_trip(self):
        payload = comparison_query([154, 874], "2025")
        self.assertEqual(payload, {"a": "154", "b": "874", "season": "2025"})
        self.assertEqual(parse_comparison_query(payload), (154, 874, "2025"))

    def test_invalid_or_incomplete_comparison_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "different"):
            comparison_query([154, 154], "2025")
        self.assertIsNone(parse_comparison_query({"a": "bad", "b": "2", "season": "x"}))
        self.assertIsNone(parse_comparison_query({"a": "1"}))

    def test_manual_comparison_does_not_rewrite_instantiated_selectors(self):
        updates = real_result_session_updates([], "2024", 101, 202)

        self.assertNotIn("real_selected_a", updates)
        self.assertNotIn("real_selected_b", updates)
        self.assertEqual(updates["real_season"], "2024")

    def test_shared_comparison_can_sync_selectors_before_they_render(self):
        updates = real_result_session_updates([], "2024", 101, 202, sync_selectors=True)

        self.assertEqual(updates["real_selected_a"], 101)
        self.assertEqual(updates["real_selected_b"], 202)


class LibraryTests(unittest.TestCase):
    def test_real_favorites_are_idempotent_and_removable(self):
        favorite = dict(PROFILES[0])
        saved = save_real_favorite({}, favorite)
        saved = save_real_favorite(saved, dict(favorite, name="Updated"))
        self.assertEqual(list(saved), ["api-1"])
        self.assertEqual(saved["api-1"]["name"], "Updated")
        self.assertEqual(remove_real_favorite(saved, "api-1"), {})

    def test_favorite_toggle_updates_a_different_season_snapshot(self):
        saved = save_real_favorite({}, dict(PROFILES[0], season="2024"))
        updated = toggle_real_favorite_snapshot(saved, dict(PROFILES[0], season="2022"))
        self.assertEqual(list(updated), ["api-1"])
        self.assertEqual(updated["api-1"]["season"], "2022")
        self.assertEqual(
            toggle_real_favorite_snapshot(updated, dict(PROFILES[0], season="2022")),
            {},
        )

    def test_real_favorites_portable_round_trip(self):
        saved = save_real_favorite({}, PROFILES[0])
        payload = real_favorites_bytes(saved)

        self.assertEqual(parse_real_favorites(payload), saved)
        self.assertNotIn(b"api_metadata", payload)

    def test_real_favorites_parser_rejects_bad_content(self):
        for payload in (
            b"not json",
            b'{"schema_version":99,"real_favorites":[]}',
            b'{"schema_version":1,"real_favorites":"bad"}',
            b'{"schema_version":1,"real_favorites":[{"player_id":"fs-a-01"}]}',
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_real_favorites(payload)

    def test_league_entries_replace_names_and_rank_by_points(self):
        entries = save_league_entry([], {"name": "Alpha", "points": 10})
        entries = save_league_entry(entries, {"name": "Beta", "points": 12})
        entries = save_league_entry(entries, {"name": "alpha", "points": 14})
        self.assertEqual([entry["name"] for entry in entries], ["alpha", "Beta"])
        self.assertEqual([entry["points"] for entry in entries], [14.0, 12.0])


if __name__ == "__main__":
    unittest.main()
