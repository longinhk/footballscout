import unittest
import tempfile
from unittest.mock import patch
from unittest.mock import Mock

import requests
from streamlit.testing.v1 import AppTest


def rendered_html(app: AppTest) -> str:
    """Return HTML component bodies for structural UI assertions."""
    return "\n".join(
        element.proto.body
        for element in app.get("html")
        if getattr(element.proto, "body", None)
    )


def by_label(elements, fragment: str):
    fragment = fragment.casefold()
    for element in elements:
        if fragment in str(getattr(element, "label", "")).casefold():
            return element
    labels = [str(getattr(element, "label", "")) for element in elements]
    raise AssertionError(f"No widget label contains {fragment!r}; found {labels!r}")


def api_response(payload):
    response = Mock()
    response.status_code = 200
    response.headers = {
        "content-type": "application/json",
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "94",
    }
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def real_player_payload(player_id: int):
    return {
        "response": [
            {
                "player": {
                    "id": player_id,
                    "name": f"Real Player {player_id}",
                    "age": 25,
                    "nationality": "Testland",
                    "height": "180 cm",
                    "injured": False,
                },
                "statistics": [
                    {
                        "team": {"name": f"Club {player_id}"},
                        "league": {"id": 39, "name": "Test League"},
                        "games": {
                            "appearences": 20,
                            "lineups": 18,
                            "minutes": 1600,
                            "position": "Attacker",
                            "rating": "7.4",
                        },
                        "goals": {"total": 10, "assists": 6},
                        "shots": {"total": 60},
                        "passes": {"key": 30, "accuracy": "82%"},
                        "tackles": {"total": 12, "interceptions": 3},
                        "duels": {"total": 100, "won": 55},
                    }
                ],
            }
        ]
    }


def real_fantasy_favorite(player_id: int, season: str):
    return {
        "api_id": player_id,
        "player_id": f"api-{player_id}",
        "name": f"Real Player {player_id}",
        "position": "Attacker",
        "nationality": "Testland",
        "team": f"Club {player_id}",
        "teams": [f"Club {player_id}"],
        "league": "Test League",
        "competitions": ["Test League"],
        "season": season,
        "games": 20,
        "minutes": 1_600,
        "goals": 10,
        "assists": 6,
        "rating": 7.4,
    }


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.disable_api = patch.dict("os.environ", {"FOOTBALLSCOUT_DISABLE_API": "1"})
        self.disable_api.start()

    def tearDown(self):
        self.disable_api.stop()

    def load_app(self) -> AppTest:
        app = AppTest.from_file("app.py", default_timeout=45)
        app.secrets = {}
        return app.run()

    def load_sample_app(self) -> AppTest:
        app = self.load_app()
        by_label(app.segmented_control, "player source").set_value(
            "Sample catalog"
        ).run()
        return app

    def test_default_app_prioritizes_real_player_search_without_exposing_a_key(self):
        app = self.load_app()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, "Compare the season. See the edge.")
        self.assertEqual(len(app.segmented_control), 2)
        self.assertEqual(
            by_label(app.segmented_control, "workspace").value, "Compare players"
        )
        self.assertEqual(
            by_label(app.segmented_control, "player source").value, "Real players"
        )
        self.assertEqual(len(app.number_input), 0)
        self.assertEqual(len(app.selectbox), 0)
        self.assertTrue(
            any(
                "server api_football_key" in item.value.casefold() for item in app.error
            )
        )

        widget_labels = " ".join(
            str(getattr(widget, "label", ""))
            for widget in [*app.text_input, *app.button, *app.selectbox]
        ).casefold()
        self.assertNotIn("api key", widget_labels)
        for field in app.text_input:
            self.assertNotEqual(getattr(field.proto, "type", ""), "password")

    def test_sample_catalog_renders_complete_matchup(self):
        app = self.load_sample_app()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            [picker.value for picker in app.selectbox[:2]],
            ["fs-a-01", "fs-a-02"],
        )

        markup = rendered_html(app)
        self.assertIn('class="fs-matchup-stage"', markup)
        self.assertIn('class="fs-duel-table"', markup)
        self.assertIn('class="fs-valuation-panel"', markup)
        self.assertIn("Adrián Vega", markup)
        self.assertIn("Malik Diallo", markup)
        self.assertIn("Context", markup)
        self.assertTrue(
            "fs-profile-grid" in markup or "fs-radar" in markup,
            "Expected the offline scouting profile visualization to render.",
        )
        self.assertGreaterEqual(len(app.get("download_button")), 3)

    def test_discovery_filters_limit_both_player_pickers(self):
        app = self.load_sample_app()
        positions = by_label(app.multiselect, "position")
        positions.set_value(["Goalkeeper"]).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.selectbox), 2)
        self.assertTrue(
            all(
                value.startswith("fs-g-")
                for value in [
                    app.selectbox[0].value,
                    app.selectbox[1].value,
                ]
            )
        )
        self.assertTrue(
            all("Goalkeeper" in option for option in app.selectbox[0].options)
        )

    def test_reset_filters_restores_the_complete_catalog(self):
        app = self.load_sample_app()
        by_label(app.multiselect, "position").set_value(["Goalkeeper"]).run()

        by_label(app.button, "reset sample filters").click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(by_label(app.multiselect, "position").value, [])
        self.assertTrue(
            any("48 of 48 sample players match" in item.value for item in app.caption)
        )

    def test_empty_search_keeps_the_last_valid_matchup_visible(self):
        app = self.load_sample_app()
        search = by_label(app.text_input, "search")
        search.set_value("no-player-can-match-this-query").run()

        self.assertEqual(list(app.exception), [])
        feedback = [item.value for item in [*app.warning, *app.info, *app.error]]
        self.assertTrue(
            any(
                "match" in value.casefold() or "player" in value.casefold()
                for value in feedback
            )
        )
        markup = rendered_html(app)
        self.assertIn("Adrián Vega", markup)
        self.assertIn("Malik Diallo", markup)

    def test_exact_player_search_keeps_an_opponent_picker_available(self):
        app = self.load_sample_app()
        by_label(app.text_input, "search").set_value("Theo Martins").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.selectbox), 2)
        self.assertEqual(app.selectbox[0].value, "fs-m-01")
        self.assertNotEqual(app.selectbox[1].value, "fs-m-01")
        self.assertIn("Theo Martins", rendered_html(app))

    def test_duplicate_selection_keeps_the_last_valid_pair(self):
        app = self.load_sample_app()
        app.selectbox[0].set_value("fs-m-01").run()
        app.selectbox[1].set_value("fs-m-01").run()

        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("different" in item.value.casefold() for item in app.error))
        markup = rendered_html(app)
        self.assertIn("Theo Martins", markup)
        self.assertIn("Malik Diallo", markup)

    def test_watchlist_action_adds_the_current_player_once(self):
        app = self.load_sample_app()
        watch_buttons = [
            button
            for button in app.button
            if (
                "watch" in button.label.casefold()
                or "shortlist" in button.label.casefold()
            )
            and (
                "player a" in button.label.casefold()
                or "adrián" in button.label.casefold()
            )
        ]
        self.assertTrue(watch_buttons, "Expected a Player A watchlist action.")

        watch_buttons[0].click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state["watchlist_ids"], ["fs-a-01"])
        markup = rendered_html(app)
        self.assertIn("Adrián Vega", markup)

    def test_sample_ui_does_not_offer_api_or_password_controls(self):
        app = self.load_sample_app()

        self.assertEqual(list(app.exception), [])
        widget_labels = " ".join(
            str(getattr(widget, "label", ""))
            for widget in [*app.text_input, *app.button, *app.selectbox]
        ).casefold()
        self.assertNotIn("api key", widget_labels)
        self.assertNotIn("live api", rendered_html(app).casefold())
        for field in app.text_input:
            self.assertNotEqual(getattr(field.proto, "type", ""), "password")

    def test_fantasy_challenge_builds_and_saves_a_one_player_team(self):
        app = self.load_app()
        by_label(app.segmented_control, "workspace").set_value(
            "Fantasy challenge"
        ).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, "Build your squad. Chase the points.")
        by_label(app.slider, "squad size").set_value(1).run()
        by_label(app.multiselect, "select exactly").set_value(["fs-a-01"]).run()
        by_label(app.text_input, "fantasy team name").set_value("Harbour XI").run()
        save_button = by_label(app.button, "save team to leaderboard")
        self.assertFalse(save_button.disabled)
        save_button.click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.session_state["fantasy_league"]), 1)
        self.assertEqual(app.session_state["fantasy_league"][0]["name"], "Harbour XI")
        self.assertIn("Session leaderboard", rendered_html(app))

    def test_real_fantasy_pool_keeps_saved_seasons_separate(self):
        app = AppTest.from_file("app.py", default_timeout=45)
        app.secrets = {}
        app.session_state["workspace_mode"] = "Fantasy challenge"
        app.session_state["fantasy_pool_mode"] = "Real favourites"
        app.session_state["real_favorites"] = {
            "api-101": real_fantasy_favorite(101, "2024"),
            "api-202": real_fantasy_favorite(202, "2024"),
            "api-303": real_fantasy_favorite(303, "2022"),
        }
        app.run()

        season = by_label(app.selectbox, "favourite season")
        self.assertEqual(season.options, ["2024", "2022"])
        self.assertEqual(season.value, "2024")
        self.assertEqual(by_label(app.slider, "squad size").value, 2)

        season.set_value("2022").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(by_label(app.slider, "squad size").value, 1)
        self.assertTrue(
            any("1 of 1 fantasy players match" in item.value for item in app.caption)
        )

    def test_free_plan_keeps_supported_seasons_when_season_catalog_fails(self):
        def request(url, **_kwargs):
            if url.endswith("/status"):
                return api_response(
                    {
                        "errors": [],
                        "response": {
                            "subscription": {"plan": "Free", "active": True},
                            "requests": {"current": 1, "limit_day": 100},
                        },
                    }
                )
            if url.endswith("/players/seasons"):
                raise requests.Timeout("catalog unavailable")
            raise AssertionError(f"Unexpected API URL: {url}")

        with tempfile.TemporaryDirectory() as cache_directory:
            with patch.dict(
                "os.environ",
                {
                    "FOOTBALLSCOUT_DISABLE_API": "0",
                    "FOOTBALLSCOUT_CACHE_PATH": f"{cache_directory}/cache.json",
                },
            ):
                with patch(
                    "data_fetcher.get_api_credentials",
                    return_value=("api-sports", "free-plan-test-key"),
                ):
                    with patch("data_fetcher.requests.get", side_effect=request):
                        app = AppTest.from_file("app.py", default_timeout=45).run()

        self.assertEqual(list(app.exception), [])
        season = by_label(app.selectbox, "season")
        self.assertEqual(season.options, ["2024", "2023", "2022"])
        self.assertEqual(season.value, "2024")

    def test_shared_real_comparison_loads_with_dynamic_seasons_and_favourites(self):
        requested_urls = []

        def request(url, *, params, **_kwargs):
            requested_urls.append(url)
            if url.endswith("/status"):
                return api_response(
                    {
                        "errors": [],
                        "response": {
                            "subscription": {"plan": "Pro", "active": True},
                            "requests": {"current": 6, "limit_day": 7500},
                        },
                    }
                )
            if url.endswith("/players/seasons"):
                return api_response({"response": [2026, 2025, 2024]})
            if url.endswith("/players"):
                return api_response(real_player_payload(int(params["id"])))
            raise AssertionError(f"Unexpected API URL: {url}")

        with tempfile.TemporaryDirectory() as cache_directory:
            with patch.dict(
                "os.environ",
                {
                    "FOOTBALLSCOUT_DISABLE_API": "0",
                    "FOOTBALLSCOUT_CACHE_PATH": f"{cache_directory}/cache.json",
                },
            ):
                with patch(
                    "data_fetcher.get_api_credentials",
                    return_value=("api-sports", "test-key"),
                ):
                    with patch("data_fetcher.requests.get", side_effect=request):
                        app = AppTest.from_file("app.py", default_timeout=45)
                        app.query_params = {"a": "101", "b": "202", "season": "2025"}
                        app.run()

                        self.assertEqual(list(app.exception), [])
                        self.assertFalse(
                            any(url.endswith("/players") for url in requested_urls)
                        )
                        by_label(app.button, "load shared comparison").click().run()

                        self.assertEqual(list(app.exception), [])
                        markup = rendered_html(app)
                        self.assertIn("Real Player 101", markup)
                        self.assertIn("Real Player 202", markup)
                        self.assertIn('class="fs-pair-profile"', markup)
                        season = by_label(app.selectbox, "season")
                        self.assertIn("2026", season.options)
                        self.assertEqual(season.value, "2025")
                        self.assertEqual(
                            by_label(app.button, "favourite player a").label,
                            "Favourite Player A",
                        )


if __name__ == "__main__":
    unittest.main()
