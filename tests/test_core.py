import math
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

import requests

from data_fetcher import FootballAPIError, fetch_player_stats, parse_player_response
from demo_data import demo_player_names, get_demo_player
from pdf_report import generate_valuation_pdf
from valuation import (
    MAX_VALUE_MILLIONS,
    calculate_value_heuristic,
    compare_methods,
    per_90,
    predict_value_ml,
)


SAMPLE_RESPONSE = {
    "response": [
        {
            "player": {"name": "Test Player", "age": 24, "photo": None},
            "statistics": [
                {
                    "team": {"name": "Test FC"},
                    "league": {"name": "Test League"},
                    "games": {
                        "appearences": 30,
                        "minutes": 2400,
                        "position": "Attacker",
                        "rating": "7.1",
                    },
                    "goals": {"total": 18, "assists": 9},
                    "tackles": {"total": 6, "interceptions": 2},
                }
            ],
        }
    ]
}


def sample_player() -> dict:
    return parse_player_response(deepcopy(SAMPLE_RESPONSE))


class DataFetcherTests(unittest.TestCase):
    def test_parser_produces_complete_schema(self):
        player = sample_player()
        self.assertEqual(player["name"], "Test Player")
        self.assertEqual(player["position"], "Attacker")
        self.assertEqual(player["saves"], 0)

    def test_empty_response_has_clear_error(self):
        with self.assertRaises(FootballAPIError):
            parse_player_response({"response": []})

    def test_parser_aggregates_all_statistics_and_weights_rating(self):
        response = deepcopy(SAMPLE_RESPONSE)
        first = response["response"][0]["statistics"][0]
        first["games"].update(
            {
                "appearences": 10,
                "minutes": 900,
                "rating": "6.0",
                "cleansheets": 1,
            }
        )
        first["goals"].update({"total": 2, "assists": 1, "conceded": 4, "saves": 5})
        first["tackles"].update({"total": 4, "interceptions": 2})

        second = deepcopy(first)
        second["team"] = {"name": "Second FC"}
        second["league"] = {"name": "Test Cup"}
        second["games"].update(
            {
                "appearences": 20,
                "minutes": 1800,
                "rating": "8.0",
                "cleansheets": 3,
            }
        )
        second["goals"].update({"total": 7, "assists": 4, "conceded": 6, "saves": 8})
        second["tackles"].update({"total": 9, "interceptions": 5})
        response["response"][0]["statistics"].append(second)

        player = parse_player_response(response, season="2025")

        self.assertEqual(player["games"], 30)
        self.assertEqual(player["minutes"], 2700)
        self.assertEqual(player["goals"], 9)
        self.assertEqual(player["assists"], 5)
        self.assertEqual(player["conceded"], 10)
        self.assertEqual(player["saves"], 13)
        self.assertEqual(player["tackles"], 13)
        self.assertEqual(player["interceptions"], 7)
        self.assertEqual(player["clean_sheets"], 4)
        self.assertAlmostEqual(player["rating"], 7.33, places=2)
        self.assertEqual(player["competition_count"], 2)
        self.assertEqual(player["scope"], "All teams and competitions")
        self.assertEqual(player["season"], "2025")

    def test_parser_coerces_null_and_malformed_numbers(self):
        response = deepcopy(SAMPLE_RESPONSE)
        player_info = response["response"][0]["player"]
        stats = response["response"][0]["statistics"][0]
        player_info["age"] = "24.0"
        stats["games"].update(
            {
                "appearences": "not-a-number",
                "minutes": None,
                "rating": "N/A",
                "cleansheets": "",
            }
        )
        stats["goals"].update(
            {"total": None, "assists": "bad", "conceded": None, "saves": ""}
        )
        stats["tackles"].update({"total": "bad", "interceptions": None})

        player = parse_player_response(response)

        self.assertEqual(player["age"], 24)
        for field in (
            "games",
            "minutes",
            "goals",
            "assists",
            "conceded",
            "saves",
            "tackles",
            "interceptions",
        ):
            with self.subTest(field=field):
                self.assertEqual(player[field], 0)
        self.assertIsNone(player["rating"])
        self.assertIsNone(player["clean_sheets"])

    def test_parser_wraps_malformed_shapes_in_domain_error(self):
        malformed_payloads = (
            None,
            [],
            {"response": "not-a-list"},
            {"response": [{}]},
            {"response": [{"player": None, "statistics": [{}]}]},
            {
                "response": [
                    {
                        "player": {"name": "Test"},
                        "statistics": [None],
                    }
                ]
            },
        )

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(FootballAPIError):
                    parse_player_response(payload)

    def test_blank_api_key_is_rejected_without_network_request(self):
        with (
            patch("data_fetcher.get_api_key", return_value=None),
            patch("data_fetcher.requests.get") as request,
        ):
            with self.assertRaises(FootballAPIError) as raised:
                fetch_player_stats(123, api_key="   ")

        request.assert_not_called()
        self.assertRegex(str(raised.exception).lower(), r"api.*key")

    def test_http_429_has_actionable_rate_limit_message(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError(
            response=Mock(status_code=429)
        )

        with patch("data_fetcher.requests.get", return_value=response):
            with self.assertRaises(FootballAPIError) as raised:
                fetch_player_stats(123, api_key="test-key")

        message = str(raised.exception).lower()
        self.assertIn("rate limit", message)
        self.assertIn("http 429", message)


class ValuationTests(unittest.TestCase):
    def test_valuations_are_non_negative(self):
        self.assertGreater(calculate_value_heuristic(sample_player()), 0)
        self.assertTrue(
            all(value >= 0 for value in compare_methods(sample_player()).values())
        )

    def test_zero_data_has_zero_value(self):
        zero_data = {
            "age": 24,
            "position": "Attacker",
            "games": 0,
            "minutes": 0,
            "goals": 0,
            "assists": 0,
            "tackles": 0,
            "interceptions": 0,
            "clean_sheets": 0,
            "saves": 0,
            "conceded": 0,
        }

        self.assertEqual(calculate_value_heuristic(zero_data), 0.0)
        self.assertTrue(
            all(value == 0.0 for value in compare_methods(zero_data).values())
        )

    def test_extreme_values_are_finite_and_clamped(self):
        extreme = {
            "age": 10**12,
            "position": "Attacker",
            "games": 10**12,
            "minutes": 10**12,
            "goals": 10**12,
            "assists": 10**12,
            "tackles": 10**12,
            "interceptions": 10**12,
            "clean_sheets": 10**12,
            "saves": 10**12,
            "conceded": 10**12,
        }
        even_more_extreme = {
            key: value * 100 if isinstance(value, int) else value
            for key, value in extreme.items()
        }

        values = compare_methods(extreme)
        saturated_values = compare_methods(even_more_extreme)
        self.assertEqual(values, saturated_values)
        for value in values.values():
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, MAX_VALUE_MILLIONS)

        non_finite = dict(extreme, goals=math.inf, assists=math.nan)
        for value in compare_methods(non_finite).values():
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, MAX_VALUE_MILLIONS)

    def test_per_90_is_public_and_handles_zero_minutes(self):
        self.assertAlmostEqual(per_90(5, 450), 1.0)
        self.assertEqual(per_90(5, 0), 0.0)
        self.assertEqual(per_90(-5, 450), 0.0)
        self.assertEqual(per_90(1000, 90), 25.0)
        self.assertEqual(per_90(1000, 90, maximum=10.0), 10.0)

    def test_ml_favorable_signals_do_not_reduce_value(self):
        attacker = sample_player()
        more_goals = dict(attacker, goals=attacker["goals"] + 5)
        self.assertGreaterEqual(
            predict_value_ml(more_goals), predict_value_ml(attacker)
        )

        goalkeeper = {
            "age": 26,
            "position": "Goalkeeper",
            "games": 30,
            "minutes": 2700,
            "rating": 7.2,
            "saves": 95,
            "clean_sheets": 10,
            "conceded": 25,
        }
        more_conceded = dict(goalkeeper, conceded=50)
        self.assertGreaterEqual(
            predict_value_ml(goalkeeper), predict_value_ml(more_conceded)
        )


class PdfReportTests(unittest.TestCase):
    def test_pdf_is_generated_in_memory(self):
        player = sample_player()
        report = generate_valuation_pdf([player, player], [compare_methods(player)] * 2)
        self.assertTrue(report.startswith(b"%PDF"))

    def test_pdf_handles_unicode_player_and_team_names(self):
        player = sample_player()
        player.update(
            {
                "name": "İlkay Gündoğan 李雷",
                "team": "Łódź United",
                "scope": "Türkiye Süper Lig",
            }
        )

        report = generate_valuation_pdf([player], [compare_methods(player)])

        self.assertTrue(report.startswith(b"%PDF"))
        self.assertGreater(len(report), 500)

    def test_pdf_rejects_mismatched_input_lengths(self):
        player = sample_player()
        values = compare_methods(player)
        mismatched_inputs = (
            ([player, player], [values]),
            ([player], [values, values]),
        )

        for players, valuations in mismatched_inputs:
            with self.subTest(
                player_count=len(players), valuation_count=len(valuations)
            ):
                with self.assertRaisesRegex(ValueError, "matching lengths"):
                    generate_valuation_pdf(players, valuations)


class DemoDataTests(unittest.TestCase):
    def test_demo_player_returns_an_isolated_copy(self):
        name = demo_player_names()[0]
        first = get_demo_player(name)
        first["name"] = "Mutated"
        first["goals"] = -999

        second = get_demo_player(name)

        self.assertEqual(second["name"], name)
        self.assertNotEqual(second["goals"], -999)

    def test_demo_player_name_list_is_isolated(self):
        names = demo_player_names()
        expected_first = names[0]
        names[0] = "Mutated"

        self.assertEqual(demo_player_names()[0], expected_first)


if __name__ == "__main__":
    unittest.main()
