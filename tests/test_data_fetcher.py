import unittest

from data_fetcher import FootballAPIError, PlayerOption, parse_player_stats


PAYLOAD = {
    "response": [
        {
            "player": {
                "id": 7,
                "name": "Ada Striker",
                "age": 23,
                "nationality": "England",
                "photo": "https://example.com/ada.png",
            },
            "statistics": [
                {
                    "team": {"name": "Code United"},
                    "league": {"name": "Premier Test"},
                    "games": {
                        "appearences": 30,
                        "minutes": 2400,
                        "position": "Attacker",
                        "rating": "7.20",
                    },
                    "goals": {"total": 18, "assists": 8},
                    "shots": {"total": 70},
                    "passes": {"total": 500, "key": 35},
                    "tackles": {"total": 8, "interceptions": 3},
                    "duels": {"won": 80},
                    "dribbles": {"success": 42},
                }
            ],
        }
    ]
}


class DataFetcherTests(unittest.TestCase):
    def test_player_option_label_is_disambiguated(self):
        option = PlayerOption(7, "Ada", 23, "England")
        self.assertIn("(7)", option.label)
        self.assertIn("England", option.label)

    def test_stats_parser_returns_complete_domain_record(self):
        player = parse_player_stats(PAYLOAD)
        self.assertEqual(player["name"], "Ada Striker")
        self.assertEqual(player["goals"], 18)
        self.assertEqual(player["saves"], 0)

    def test_stats_parser_rejects_empty_response(self):
        with self.assertRaises(FootballAPIError):
            parse_player_stats({"response": []})


if __name__ == "__main__":
    unittest.main()
