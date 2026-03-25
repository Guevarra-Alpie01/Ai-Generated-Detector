from django.test import SimpleTestCase

from detector.services.scoring import clamp_score, label_from_probability


class ScoringUtilityTests(SimpleTestCase):
    def test_clamp_score_bounds_value(self):
        self.assertEqual(clamp_score(4), 1.0)
        self.assertEqual(clamp_score(-2), 0.0)

    def test_label_from_probability_returns_predicted_label_confidence(self):
        label, confidence = label_from_probability(0.82, threshold=0.58)
        self.assertEqual(label, "AI-generated")
        self.assertAlmostEqual(confidence, 82.0)
