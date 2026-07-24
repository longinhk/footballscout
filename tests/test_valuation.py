import unittest

from explanations import deterministic_explanation
from pdf_report import generate_valuation_pdf
from test_data_fetcher import PAYLOAD
from data_fetcher import parse_player_stats
from valuation import evaluate_demo_model, predict_value


class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.player = parse_player_stats(PAYLOAD)

    def test_prediction_is_positive_and_reproducible(self):
        first = predict_value(self.player)
        second = predict_value(self.player)
        self.assertGreater(first.value_millions, 0)
        self.assertEqual(first, second)

    def test_evaluation_has_expected_metrics(self):
        metrics = evaluate_demo_model()
        self.assertGreater(metrics["test_rows"], 0)
        self.assertGreaterEqual(metrics["mae_millions"], 0)

    def test_explanation_is_grounded_and_warns_about_status(self):
        value = predict_value(self.player)
        explanation = deterministic_explanation(self.player, self.player, value, value)
        self.assertIn(self.player["name"], explanation)
        self.assertIn("not evidence", explanation)

    def test_pdf_is_generated_in_memory(self):
        value = predict_value(self.player)
        report = generate_valuation_pdf([self.player] * 2, [value] * 2, "Test explanation")
        self.assertTrue(report.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
