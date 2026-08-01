import math
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from demo_data import (
    DATASET_VERSION,
    POSITION_ORDER,
    all_demo_players,
    catalog_leagues,
    catalog_positions,
    demo_player_ids,
    demo_player_names,
    get_demo_player,
    get_demo_player_by_id,
    player_label,
    search_demo_players,
)
from pdf_report import generate_valuation_pdf
from scouting import (
    PROFILE_DIMENSIONS,
    add_to_watchlist,
    form_summary,
    parse_workspace,
    profile_percentiles,
    remove_from_watchlist,
    save_matchup,
    workspace_bytes,
)
from ui_components import MetricSpec, metric_value
from valuation import (
    MAX_VALUE_MILLIONS,
    calculate_context_value,
    calculate_value_heuristic,
    compare_methods,
    per_90,
    predict_value_ml,
    valuation_confidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sample_player(name: str = "Adrián Vega") -> dict:
    return get_demo_player(name)


class OfflineCatalogTests(unittest.TestCase):
    def test_catalog_has_48_balanced_fictional_players(self):
        players = all_demo_players()

        self.assertEqual(len(players), 48)
        self.assertEqual(
            Counter(player["position"] for player in players),
            {
                "Attacker": 12,
                "Midfielder": 12,
                "Defender": 12,
                "Goalkeeper": 12,
            },
        )
        self.assertEqual(catalog_positions(), list(POSITION_ORDER))
        self.assertEqual(len(catalog_leagues()), 4)
        self.assertTrue(
            all(player["data_source"] == "fictional_offline" for player in players)
        )
        self.assertTrue(
            all(player["dataset_version"] == DATASET_VERSION for player in players)
        )

    def test_catalog_ids_are_unique_stable_and_resolvable(self):
        ids = demo_player_ids()

        self.assertEqual(len(ids), 48)
        self.assertEqual(len(set(ids)), 48)
        self.assertEqual(ids[:2], ["fs-a-01", "fs-a-02"])
        self.assertEqual(ids[12], "fs-m-01")
        for player_id in ids:
            player = get_demo_player_by_id(player_id)
            self.assertEqual(player["player_id"], player_id)
            self.assertIn(player["name"], player_label(player_id))

    def test_catalog_records_have_the_offline_scouting_schema(self):
        required = {
            "player_id",
            "name",
            "team",
            "league",
            "position",
            "age",
            "minutes",
            "rating",
            "form",
            "contract_years",
            "injury_risk",
            "league_strength",
            "club_selling_power",
            "recent_fee",
            "progressive_actions",
        }

        for player in all_demo_players():
            with self.subTest(player=player["player_id"]):
                self.assertTrue(required.issubset(player))
                self.assertEqual(len(player["form"]), 6)
                self.assertGreater(player["minutes"], 0)

    def test_catalog_accessors_return_isolated_copies(self):
        player_id = demo_player_ids()[0]
        first = get_demo_player_by_id(player_id)
        first["name"] = "Mutated"
        first["form"][0] = -999

        restored = get_demo_player_by_id(player_id)
        self.assertNotEqual(restored["name"], "Mutated")
        self.assertNotEqual(restored["form"][0], -999)

        roster = all_demo_players()
        roster.pop()
        self.assertEqual(len(all_demo_players()), 48)

        names = demo_player_names()
        names[0] = "Mutated"
        self.assertEqual(demo_player_names()[0], "Adrián Vega")

    def test_search_is_accent_insensitive_and_checks_context_fields(self):
        self.assertEqual(
            [player["name"] for player in search_demo_players("adrian")],
            ["Adrián Vega"],
        )
        self.assertIn(
            "João Costa",
            [player["name"] for player in search_demo_players("joao")],
        )
        self.assertTrue(search_demo_players("Northbridge"))
        self.assertTrue(search_demo_players("Continental League"))
        self.assertEqual(search_demo_players("definitely-not-a-player"), [])

    def test_filters_can_be_combined_without_mutating_catalog(self):
        before = all_demo_players()
        matches = search_demo_players(
            positions={"Defender"},
            leagues={"Pacific League"},
            age_range=(20, 28),
            minimum_minutes=1_800,
        )

        self.assertTrue(matches)
        self.assertTrue(all(player["position"] == "Defender" for player in matches))
        self.assertTrue(all(player["league"] == "Pacific League" for player in matches))
        self.assertTrue(all(20 <= player["age"] <= 28 for player in matches))
        self.assertTrue(all(player["minutes"] >= 1_800 for player in matches))
        matches[0]["team"] = "Mutated"
        self.assertEqual(all_demo_players(), before)

    def test_unknown_catalog_lookups_raise_clear_errors(self):
        with self.assertRaisesRegex(KeyError, "Unknown demo player"):
            get_demo_player("Nobody")
        with self.assertRaisesRegex(KeyError, "Unknown offline player ID"):
            get_demo_player_by_id("fs-x-99")


class ScoutingTests(unittest.TestCase):
    def test_profile_percentiles_cover_six_dimensions_and_role_cohort(self):
        roster = all_demo_players()
        player = sample_player()
        scores = profile_percentiles(player, roster)

        self.assertEqual(tuple(scores), PROFILE_DIMENSIONS)
        self.assertEqual(len(scores), 6)
        self.assertTrue(all(isinstance(score, int) for score in scores.values()))
        self.assertTrue(all(0 <= score <= 100 for score in scores.values()))

        attacker_only = [item for item in roster if item["position"] == "Attacker"]
        self.assertEqual(scores, profile_percentiles(player, attacker_only))

    def test_form_summary_reports_direction_average_and_missing_data(self):
        summary = form_summary(sample_player())

        self.assertEqual(summary["direction"], "Rising")
        self.assertEqual(len(summary["values"]), 6)
        self.assertGreater(summary["average"], 7.0)
        self.assertGreater(summary["delta"], 0)
        self.assertEqual(
            form_summary({"form": []}),
            {"values": [], "average": None, "delta": 0.0, "direction": "No data"},
        )

    def test_watchlist_helpers_are_ordered_idempotent_and_validate_ids(self):
        valid_ids = set(demo_player_ids())
        first_id, second_id = demo_player_ids()[:2]

        watchlist = add_to_watchlist([], first_id, valid_ids)
        watchlist = add_to_watchlist(watchlist, first_id, valid_ids)
        watchlist = add_to_watchlist(watchlist, second_id, valid_ids)
        self.assertEqual(watchlist, [first_id, second_id])
        self.assertEqual(remove_from_watchlist(watchlist, first_id), [second_id])
        with self.assertRaisesRegex(ValueError, "Unknown offline player ID"):
            add_to_watchlist(watchlist, "fs-x-99", valid_ids)

    def test_saved_matchups_are_distinct_and_idempotent(self):
        first_id, second_id = demo_player_ids()[:2]
        saved = save_matchup([], first_id, second_id)
        saved = save_matchup(saved, first_id, second_id)

        self.assertEqual(saved, [[first_id, second_id]])
        self.assertEqual(
            save_matchup(saved, second_id, first_id),
            [[first_id, second_id], [second_id, first_id]],
        )
        with self.assertRaisesRegex(ValueError, "two different players"):
            save_matchup(saved, first_id, first_id)

    def test_workspace_round_trip_deduplicates_and_preserves_order(self):
        ids = demo_player_ids()
        payload = workspace_bytes(
            [ids[0], ids[1], ids[0]],
            [[ids[0], ids[1]], [ids[2], ids[3]]],
        )

        watchlist, matchups = parse_workspace(payload, set(ids))
        self.assertEqual(watchlist, ids[:2])
        self.assertEqual(matchups, [[ids[0], ids[1]], [ids[2], ids[3]]])

    def test_workspace_parser_rejects_unknown_or_malformed_content(self):
        valid_ids = set(demo_player_ids())
        invalid_payloads = (
            b"not json",
            '{"schema_version": 99}',
            '{"schema_version": 1, "watchlist_ids": "bad", "saved_matchups": []}',
            '{"schema_version": 1, "watchlist_ids": ["fs-x-99"], "saved_matchups": []}',
            '{"schema_version": 1, "watchlist_ids": [], "saved_matchups": [["fs-a-01", "fs-a-01"]]}',
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_workspace(payload, valid_ids)

    def test_goalkeeping_metrics_are_unavailable_for_outfield_players(self):
        conceded_per_90 = MetricSpec(
            "Goalkeeping",
            "Goals conceded / 90",
            "conceded",
            decimals=2,
            rate=True,
            direction="lower",
        )

        self.assertIsNone(metric_value(sample_player(), conceded_per_90))
        self.assertGreater(
            metric_value(get_demo_player("Hana Sato"), conceded_per_90), 0
        )


class ValuationTests(unittest.TestCase):
    def test_three_valuation_methods_are_non_negative_and_bounded(self):
        methods = compare_methods(sample_player())

        self.assertEqual(tuple(methods), ("Heuristic", "Demo ML", "Context"))
        self.assertGreater(calculate_value_heuristic(sample_player()), 0)
        self.assertGreater(calculate_context_value(sample_player()), 0)
        for value in methods.values():
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, MAX_VALUE_MILLIONS)

    def test_context_method_responds_to_contract_and_injury_context(self):
        favorable = sample_player()
        unfavorable = deepcopy(favorable)
        favorable.update(contract_years=5, injury_risk="Low")
        unfavorable.update(contract_years=0, injury_risk="High")

        self.assertGreater(
            calculate_context_value(favorable),
            calculate_context_value(unfavorable),
        )

    def test_confidence_is_bounded_and_contains_the_method_average(self):
        player = sample_player()
        methods = compare_methods(player)
        confidence = valuation_confidence(player, methods)
        average = sum(methods.values()) / len(methods)

        self.assertIn(confidence["label"], {"Low", "Medium", "High"})
        self.assertTrue(0 <= confidence["score"] <= 100)
        self.assertLessEqual(confidence["low"], min(methods.values()))
        self.assertGreaterEqual(confidence["high"], max(methods.values()))
        self.assertLessEqual(confidence["low"], average)
        self.assertGreaterEqual(confidence["high"], average)
        self.assertLessEqual(confidence["high"], MAX_VALUE_MILLIONS)

    def test_zero_data_has_zero_value_and_low_confidence(self):
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

        self.assertEqual(
            compare_methods(zero_data),
            {
                "Heuristic": 0.0,
                "Demo ML": 0.0,
                "Context": 0.0,
            },
        )
        self.assertEqual(
            valuation_confidence(zero_data),
            {"score": 0, "label": "Low", "low": 0.0, "high": 0.0},
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
            "contract_years": 10**12,
            "league_strength": 10**12,
            "club_selling_power": 10**12,
            "recent_fee": 10**12,
        }
        even_more_extreme = {
            key: value * 100 if isinstance(value, int) else value
            for key, value in extreme.items()
        }

        values = compare_methods(extreme)
        self.assertEqual(values, compare_methods(even_more_extreme))
        for value in values.values():
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, MAX_VALUE_MILLIONS)

        non_finite = dict(extreme, goals=math.inf, assists=math.nan)
        self.assertTrue(
            all(math.isfinite(value) for value in compare_methods(non_finite).values())
        )

    def test_per_90_is_public_and_handles_bad_minutes(self):
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

        goalkeeper = get_demo_player("Hana Sato")
        more_conceded = dict(goalkeeper, conceded=goalkeeper["conceded"] + 20)
        self.assertGreaterEqual(
            predict_value_ml(goalkeeper),
            predict_value_ml(more_conceded),
        )


class PdfReportTests(unittest.TestCase):
    def test_pdf_is_generated_in_memory_with_all_three_methods(self):
        players = [sample_player(), get_demo_player("Malik Diallo")]
        report = generate_valuation_pdf(
            players, [compare_methods(player) for player in players]
        )

        self.assertTrue(report.startswith(b"%PDF"))
        self.assertGreater(len(report), 800)

    def test_pdf_handles_unicode_player_and_team_names(self):
        player = sample_player()
        player.update(name="İlkay Gündoğan 李雷", team="Łódź United", scope="Türkiye")

        report = generate_valuation_pdf([player], [compare_methods(player)])

        self.assertTrue(report.startswith(b"%PDF"))
        self.assertGreater(len(report), 500)

    def test_pdf_rejects_mismatched_input_lengths(self):
        player = sample_player()
        values = compare_methods(player)
        with self.assertRaisesRegex(ValueError, "matching lengths"):
            generate_valuation_pdf([player, player], [values])


class RuntimeArchitectureTests(unittest.TestCase):
    def test_runtime_supports_server_side_real_search_and_sample_fallback(self):
        app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8").casefold()
        requirements = (
            (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").casefold()
        )
        secrets_example = (
            PROJECT_ROOT / ".streamlit" / "secrets.example.toml"
        ).read_text(encoding="utf-8")

        self.assertIn("data_fetcher", app_source)
        self.assertIn('("real players", "sample catalog")', app_source)
        self.assertIn("requests", requirements)
        self.assertTrue((PROJECT_ROOT / "data_fetcher.py").exists())
        self.assertIn("API_FOOTBALL_KEY", secrets_example)
        self.assertNotIn("your-private-key", secrets_example)


if __name__ == "__main__":
    unittest.main()
