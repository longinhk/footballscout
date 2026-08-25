from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from data_fetcher import (
    DIRECT_API_ROOT,
    HTTP_TIMEOUT,
    FootballAPIError,
    age_for_season,
    clear_disk_cache,
    fetch_account_status,
    fetch_available_seasons,
    fetch_available_seasons_with_metadata,
    fetch_player_stats,
    filter_player_profiles,
    parse_account_status,
    parse_player_response,
    parse_profile_response,
    parse_seasons_response,
    search_player_profiles,
    search_player_profiles_with_metadata,
)


PROFILE_RESPONSE = {
    "response": [
        {
            "player": {
                "id": 154,
                "name": "L. Messi",
                "firstname": "Lionel Andrés",
                "lastname": "Messi Cuccittini",
                "age": 39,
                "nationality": "Argentina",
                "height": "170 cm",
                "position": "Attacker",
                "photo": "https://media.example/messi.png",
            }
        }
    ]
}


PLAYER_RESPONSE = {
    "parameters": {"id": "154", "season": "2025"},
    "results": 1,
    "response": [
        {
            "player": {
                "id": 154,
                "name": "L. Messi",
                "age": 39,
                "nationality": "Argentina",
                "height": "170 cm",
                "injured": False,
            },
            "statistics": [
                {
                    "team": {"name": "Inter Miami"},
                    "league": {"id": 253, "name": "Major League Soccer"},
                    "games": {
                        "appearences": 18,
                        "lineups": 17,
                        "minutes": 1500,
                        "position": "Attacker",
                        "rating": "7.80",
                    },
                    "goals": {"total": 16, "assists": 9},
                    "shots": {"total": 80},
                    "passes": {"key": 48, "accuracy": "84%"},
                    "tackles": {"total": 7, "interceptions": 2},
                    "duels": {"total": 120, "won": 66},
                }
            ],
        }
    ],
}


def provider_response(payload, *, status=200, headers=None, text=""):
    response = Mock()
    response.status_code = status
    response.headers = headers or {}
    response.text = text
    response.json.return_value = payload
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class CacheIsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.temp_directory.name) / "api-cache.json"

    def tearDown(self):
        self.temp_directory.cleanup()


class ProfileSearchTests(CacheIsolatedTestCase):
    def test_profile_parser_normalizes_and_deduplicates_results(self):
        payload = {"response": PROFILE_RESPONSE["response"] * 2}

        profiles = parse_profile_response(payload)

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["api_id"], 154)
        self.assertEqual(profiles[0]["name"], "L. Messi")
        self.assertEqual(profiles[0]["height_cm"], 170)
        self.assertEqual(profiles[0]["nationality"], "Argentina")

    def test_search_requires_one_four_character_name_token(self):
        with patch("data_fetcher.requests.get") as request:
            with self.assertRaisesRegex(FootballAPIError, "at least 4"):
                search_player_profiles("Li An", api_key="secret")
        request.assert_not_called()

    @patch("data_fetcher.requests.get")
    def test_direct_search_uses_server_header_and_profile_endpoint(self, request):
        request.return_value = provider_response(PROFILE_RESPONSE)

        profiles = search_player_profiles("Messi", api_key="secret", use_cache=False)

        self.assertEqual(profiles[0]["api_id"], 154)
        request.assert_called_once_with(
            f"{DIRECT_API_ROOT}/players/profiles",
            headers={"x-apisports-key": "secret"},
            params={"search": "Messi"},
            timeout=HTTP_TIMEOUT,
        )

    @patch("data_fetcher.requests.get")
    def test_full_name_uses_surname_and_stops_after_a_confident_match(self, request):
        request.return_value = provider_response(PROFILE_RESPONSE)

        profiles, metadata = search_player_profiles_with_metadata(
            "Lionel Messi", api_key="secret", use_cache=False
        )

        self.assertEqual(profiles[0]["api_id"], 154)
        self.assertEqual(metadata["queries"], ["Messi"])
        self.assertEqual(request.call_count, 1)

    @patch("data_fetcher.requests.get")
    def test_reversed_name_falls_back_and_ranks_the_complete_match_first(self, request):
        unrelated = {
            "response": [
                {
                    "player": {
                        "id": 999,
                        "name": "A. Lionel",
                        "firstname": "Alex",
                        "lastname": "Lionel",
                        "position": "Defender",
                    }
                }
            ]
        }
        request.side_effect = [
            provider_response(unrelated),
            provider_response(PROFILE_RESPONSE),
        ]

        profiles, metadata = search_player_profiles_with_metadata(
            "Messi Lionel", api_key="secret", use_cache=False
        )

        self.assertEqual(metadata["queries"], ["Lionel", "Messi"])
        self.assertEqual(profiles[0]["api_id"], 154)
        self.assertEqual(request.call_count, 2)

    @patch("data_fetcher.requests.get")
    def test_accented_surname_uses_an_ascii_safe_provider_query(self, request):
        mbappe = {
            "response": [
                {
                    "player": {
                        "id": 278,
                        "name": "K. Mbappé",
                        "firstname": "Kylian",
                        "lastname": "Mbappé Lottin",
                        "position": "Attacker",
                    }
                }
            ]
        }
        request.return_value = provider_response(mbappe)

        profiles = search_player_profiles(
            "Kylian Mbappé", api_key="secret", use_cache=False
        )

        self.assertEqual(profiles[0]["api_id"], 278)
        self.assertEqual(request.call_args.kwargs["params"], {"search": "mbappe"})

    @patch("data_fetcher.requests.get")
    def test_fallback_search_is_strictly_bounded_to_three_requests(self, request):
        request.return_value = provider_response({"response": []})

        profiles, metadata = search_player_profiles_with_metadata(
            "Alpha Bravo Charlie Delta", api_key="secret", use_cache=False
        )

        self.assertEqual(profiles, [])
        self.assertEqual(metadata["queries"], ["Delta", "Charlie", "Bravo"])
        self.assertEqual(request.call_count, 3)

    def test_profile_filters_are_case_insensitive_and_do_not_mutate_input(self):
        profiles = parse_profile_response(PROFILE_RESPONSE)
        original = dict(profiles[0])

        filtered = filter_player_profiles(
            profiles,
            positions="attacker",
            nationalities=["ARGENTINA"],
            min_age=30,
            max_age=40,
        )

        self.assertEqual([profile["api_id"] for profile in filtered], [154])
        self.assertEqual(profiles[0], original)
        self.assertEqual(filter_player_profiles(profiles, max_age=25), [])

    def test_profile_filter_rejects_an_inverted_age_range(self):
        with self.assertRaisesRegex(ValueError, "min_age"):
            filter_player_profiles([], min_age=30, max_age=20)


class PersistentCacheTests(CacheIsolatedTestCase):
    @patch("data_fetcher.requests.get")
    def test_second_search_uses_disk_cache_without_storing_the_key(self, request):
        request.return_value = provider_response(
            PROFILE_RESPONSE,
            headers={
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "99",
            },
        )

        first, first_metadata = search_player_profiles_with_metadata(
            "Messi", api_key="first-secret", cache_path=self.cache_path
        )
        second, second_metadata = search_player_profiles_with_metadata(
            "Messi", api_key="second-secret", cache_path=self.cache_path
        )

        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)
        self.assertFalse(first_metadata["all_cache_hits"])
        self.assertTrue(second_metadata["all_cache_hits"])
        self.assertEqual(second_metadata["quota"], {"limit": 100, "remaining": 99})
        cache_text = self.cache_path.read_text(encoding="utf-8")
        self.assertNotIn("first-secret", cache_text)
        self.assertNotIn("second-secret", cache_text)

    @patch("data_fetcher.requests.get")
    def test_expired_entry_is_refetched(self, request):
        request.return_value = provider_response(PROFILE_RESPONSE)
        search_player_profiles("Messi", api_key="secret", cache_path=self.cache_path)
        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        for entry in cache["entries"].values():
            entry["expires_at"] = 0
        self.cache_path.write_text(json.dumps(cache), encoding="utf-8")

        search_player_profiles("Messi", api_key="secret", cache_path=self.cache_path)

        self.assertEqual(request.call_count, 2)

    @patch("data_fetcher.time.sleep")
    @patch("data_fetcher.requests.get")
    def test_transient_outage_serves_expired_cache(self, request, sleep):
        request.return_value = provider_response(PROFILE_RESPONSE)
        search_player_profiles("Messi", api_key="secret", cache_path=self.cache_path)
        cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        for entry in cache["entries"].values():
            entry["expires_at"] = 0
        self.cache_path.write_text(json.dumps(cache), encoding="utf-8")
        request.side_effect = requests.Timeout("provider unavailable")

        profiles, metadata = search_player_profiles_with_metadata(
            "Messi", api_key="secret", cache_path=self.cache_path
        )

        self.assertEqual(profiles[0]["api_id"], 154)
        self.assertTrue(metadata["used_stale_fallback"])
        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_count, 2)

    @patch("data_fetcher.requests.get")
    def test_corrupt_cache_is_discarded_and_rebuilt(self, request):
        self.cache_path.write_text("{not-json", encoding="utf-8")
        request.return_value = provider_response(PROFILE_RESPONSE)

        profiles = search_player_profiles(
            "Messi", api_key="secret", cache_path=self.cache_path
        )

        self.assertEqual(profiles[0]["api_id"], 154)
        rebuilt = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["version"], 1)

    def test_cache_can_be_cleared_explicitly(self):
        self.cache_path.write_text("{}", encoding="utf-8")

        self.assertTrue(clear_disk_cache(self.cache_path))
        self.assertFalse(self.cache_path.exists())
        self.assertFalse(clear_disk_cache(self.cache_path))


class AccountStatusTests(CacheIsolatedTestCase):
    def test_status_parser_excludes_account_identity(self):
        status = parse_account_status(
            {
                "response": {
                    "account": {"email": "owner@example.com"},
                    "subscription": {"plan": "Free", "active": True},
                    "requests": {"current": 5, "limit_day": 100},
                }
            }
        )

        self.assertEqual(
            status,
            {
                "plan": "Free",
                "active": True,
                "requests_current": 5,
                "requests_limit": 100,
            },
        )
        self.assertNotIn("account", status)

    @patch("data_fetcher.requests.get")
    def test_status_request_is_not_written_to_disk(self, request):
        response = Mock()
        response.headers = {}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "errors": [],
            "response": {
                "account": {"email": "owner@example.com"},
                "subscription": {"plan": "Free", "active": True},
                "requests": {"current": 5, "limit_day": 100},
            },
        }
        request.return_value = response

        status = fetch_account_status(api_key="secret", provider="api-sports")

        self.assertEqual(status["plan"], "Free")
        self.assertFalse(self.cache_path.exists())
        self.assertTrue(request.call_args.args[0].endswith("/status"))


class AvailableSeasonsTests(CacheIsolatedTestCase):
    def test_season_parser_deduplicates_sorts_and_discards_invalid_values(self):
        seasons = parse_seasons_response(
            {"response": [2023, "2025", 2024, 2025, "bad", 1899, None]}
        )

        self.assertEqual(seasons, [2025, 2024, 2023])

    @patch("data_fetcher.requests.get")
    def test_seasons_can_be_limited_to_a_player(self, request):
        request.return_value = provider_response(
            {"response": [2025, 2024], "results": 2},
            headers={"x-ratelimit-requests-remaining": "87"},
        )

        seasons, metadata = fetch_available_seasons_with_metadata(
            154,
            api_key="secret",
            cache_path=self.cache_path,
            use_cache=False,
        )

        self.assertEqual(seasons, [2025, 2024])
        self.assertEqual(metadata["player_id"], 154)
        self.assertEqual(metadata["season_count"], 2)
        self.assertEqual(metadata["quota"]["remaining"], 87)
        self.assertEqual(request.call_args.kwargs["params"], {"player": 154})
        self.assertTrue(request.call_args.args[0].endswith("/players/seasons"))

    @patch("data_fetcher.requests.get")
    def test_global_seasons_send_no_player_parameter(self, request):
        request.return_value = provider_response({"response": [2025]})

        seasons = fetch_available_seasons(api_key="secret", use_cache=False)

        self.assertEqual(seasons, [2025])
        self.assertEqual(request.call_args.kwargs["params"], {})

    def test_seasons_reject_an_invalid_player_id_before_network_use(self):
        with patch("data_fetcher.requests.get") as request:
            with self.assertRaisesRegex(FootballAPIError, "positive integer"):
                fetch_available_seasons(-1, api_key="secret")
        request.assert_not_called()


class ProviderErrorTests(CacheIsolatedTestCase):
    @patch("data_fetcher.time.sleep")
    @patch("data_fetcher.requests.get")
    def test_transient_response_is_retried_before_success(self, request, sleep):
        request.side_effect = [
            provider_response({}, status=503, headers={"Retry-After": "1"}),
            provider_response(PROFILE_RESPONSE),
        ]

        profiles = search_player_profiles("Messi", api_key="secret", use_cache=False)

        self.assertEqual(profiles[0]["api_id"], 154)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1.0)
    @patch("data_fetcher.requests.get")
    def test_rate_limit_has_a_clear_message(self, request):
        request.return_value = provider_response(
            {"errors": {"rateLimit": "Daily quota exhausted"}}, status=429
        )

        with self.assertRaisesRegex(FootballAPIError, "daily limit"):
            search_player_profiles("Messi", api_key="secret", use_cache=False)

    @patch("data_fetcher.requests.get")
    def test_403_invalid_key_reports_provider_detail_and_redacts_key(self, request):
        secret = "private-owner-key"
        request.return_value = provider_response(
            {"errors": {"token": f"Invalid API key {secret}"}}, status=403
        )

        with self.assertRaises(FootballAPIError) as caught:
            search_player_profiles("Messi", api_key=secret, use_cache=False)

        message = str(caught.exception)
        self.assertIn("key was rejected", message)
        self.assertIn("Invalid API key", message)
        self.assertNotIn(secret, message)

    @patch("data_fetcher.requests.get")
    def test_403_ip_restriction_is_distinguished_from_a_plan_error(self, request):
        request.return_value = provider_response(
            {"message": "IP address is not allowed"}, status=403
        )

        with self.assertRaisesRegex(FootballAPIError, "server's IP"):
            search_player_profiles("Messi", api_key="secret", use_cache=False)

    @patch("data_fetcher.requests.get")
    def test_403_subscription_detail_is_reported_as_a_plan_error(self, request):
        request.return_value = provider_response(
            {"errors": {"subscription": "This plan has no access"}}, status=403
        )

        with self.assertRaises(FootballAPIError) as caught:
            search_player_profiles("Messi", api_key="secret", use_cache=False)

        self.assertIn("plan does not allow", str(caught.exception))
        self.assertNotIn("server's IP", str(caught.exception))

    @patch("data_fetcher.requests.get")
    def test_provider_error_in_a_success_response_also_redacts_the_key(self, request):
        secret = "private-owner-key"
        request.return_value = provider_response(
            {"errors": {"token": f"Rejected {secret}"}}
        )

        with self.assertRaises(FootballAPIError) as caught:
            search_player_profiles("Messi", api_key=secret, use_cache=False)

        self.assertIn("token: Rejected", str(caught.exception))
        self.assertNotIn(secret, str(caught.exception))


class PlayerSeasonTests(CacheIsolatedTestCase):
    def test_age_is_derived_for_the_historical_season(self):
        payload = deepcopy(PLAYER_RESPONSE)
        payload["response"][0]["player"].update(
            {
                "birth": {"date": "1987-06-24"},
                "age": 39,
                "injured": True,
            }
        )

        player = parse_player_response(payload, season="2022")

        self.assertEqual(age_for_season("1987-06-24", "2022"), 35)
        self.assertEqual(player["age"], 35)
        self.assertEqual(player["age_source"], "birth_date")
        self.assertEqual(player["age_reference"], "2022-12-31")
        self.assertEqual(player["injury_risk"], "Unknown")

    def test_player_parser_aggregates_a_season_without_inventing_fields(self):
        player = parse_player_response(PLAYER_RESPONSE, season="2025")

        self.assertEqual(player["player_id"], "api-154")
        self.assertEqual(player["games"], 18)
        self.assertEqual(player["minutes"], 1500)
        self.assertEqual(player["goals"], 16)
        self.assertEqual(player["assists"], 9)
        self.assertEqual(player["pass_accuracy"], 84.0)
        self.assertEqual(player["duels_won_pct"], 55.0)
        self.assertIsNone(player["progressive_actions"])
        self.assertEqual(player["data_source"], "api_football")
        self.assertEqual(
            player["api_metadata"]["coverage"], {"id": "154", "season": "2025"}
        )

    @patch("data_fetcher.requests.get")
    def test_fetch_uses_player_id_and_season(self, request):
        request.return_value = provider_response(PLAYER_RESPONSE)

        player = fetch_player_stats(154, "2025", api_key="secret", use_cache=False)

        self.assertEqual(player["name"], "L. Messi")
        self.assertEqual(
            request.call_args.kwargs["params"], {"id": 154, "season": "2025"}
        )

    def test_empty_season_response_has_a_clear_recovery_hint(self):
        with self.assertRaisesRegex(FootballAPIError, "Try another season"):
            parse_player_response({"response": []}, season="2025")


if __name__ == "__main__":
    unittest.main()
