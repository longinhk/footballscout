import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from demo_data import get_demo_player


def rendered_html(app: AppTest) -> str:
    """Return the bodies emitted by st.html for structural UI assertions."""
    return "\n".join(
        element.proto.body
        for element in app.get("html")
        if getattr(element.proto, "body", None)
    )


class AppSmokeTests(unittest.TestCase):
    def test_default_demo_renders_complete_matchup(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, "Compare the season. See the edge.")
        self.assertEqual(app.segmented_control[0].value, "Demo data")
        self.assertEqual(
            [picker.value for picker in app.selectbox],
            ["Adrián Vega", "Malik Diallo"],
        )

        markup = rendered_html(app)
        self.assertIn('class="fs-matchup-stage"', markup)
        self.assertIn('class="fs-duel-table"', markup)
        self.assertIn('class="fs-valuation-panel"', markup)
        self.assertIn("Adrián Vega", markup)
        self.assertIn("Malik Diallo", markup)
        self.assertEqual(len(app.get("download_button")), 2)

    def test_demo_duplicate_selection_keeps_last_valid_matchup(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        app.selectbox[0].set_value("Theo Martins").run()
        app.selectbox[1].set_value("Theo Martins").run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("Choose two different players", app.error[0].value)
        self.assertEqual(
            app.session_state["demo_result_names"],
            ("Theo Martins", "Malik Diallo"),
        )
        markup = rendered_html(app)
        self.assertIn("Theo Martins", markup)
        self.assertIn("Malik Diallo", markup)

    def test_live_mode_without_result_has_a_guided_empty_state(self):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": ""}):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            app.segmented_control[0].set_value("Live API").run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("Set up a live comparison", app.info[0].value)
        self.assertEqual(len(app.get("download_button")), 0)

    def test_server_api_key_is_not_sent_to_password_widget(self):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": "server-side-secret"}):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            app.segmented_control[0].set_value("Live API").run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.text_input[0].value, "")

    def test_live_submit_requires_an_api_key(self):
        with patch.dict(os.environ, {"RAPIDAPI_KEY": ""}):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            app.segmented_control[0].set_value("Live API").run()
            app.button[0].click().run()

        self.assertEqual(list(app.exception), [])
        self.assertIn("Enter an API-Football key", app.error[0].value)
        self.assertEqual(len(app.get("download_button")), 0)

    def test_successful_live_submit_renders_players_with_the_same_name(self):
        first = deepcopy(get_demo_player("Adrián Vega"))
        second = deepcopy(get_demo_player("Malik Diallo"))
        first.update({"name": "Alex Silva", "team": "Northside FC"})
        second.update({"name": "Alex Silva", "team": "Southbank FC"})

        with (
            patch.dict(os.environ, {"RAPIDAPI_KEY": ""}),
            patch(
                "data_fetcher.fetch_player_stats", side_effect=[first, second]
            ) as fetch,
        ):
            app = AppTest.from_file("app.py", default_timeout=30).run()
            app.segmented_control[0].set_value("Live API").run()
            app.number_input[0].set_value(2024)
            app.number_input[1].set_value(918271)
            app.number_input[2].set_value(918272)
            app.text_input[0].set_value("temporary-test-key")
            app.button[0].click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(
            [player["name"] for player in app.session_state["live_result"]["players"]],
            ["Alex Silva", "Alex Silva"],
        )
        self.assertIn("Northside FC", rendered_html(app))
        self.assertIn("Southbank FC", rendered_html(app))
        self.assertEqual(len(app.get("download_button")), 2)


if __name__ == "__main__":
    unittest.main()
