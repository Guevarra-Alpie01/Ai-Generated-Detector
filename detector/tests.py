from django.test import SimpleTestCase

from detector.services.detection import DetectionOrchestrator
from detector.services.scoring import clamp_score, label_from_probability, weighted_score


class ScoringUtilityTests(SimpleTestCase):
    def test_clamp_score_bounds_value(self):
        self.assertEqual(clamp_score(4), 1.0)
        self.assertEqual(clamp_score(-2), 0.0)

    def test_label_from_probability_returns_predicted_label_confidence(self):
        label, confidence = label_from_probability(0.82, threshold=0.58)
        self.assertEqual(label, "AI-generated")
        self.assertAlmostEqual(confidence, 82.0)

    def test_weighted_score_ignores_missing_components(self):
        score = weighted_score(
            {
                "model_score": None,
                "metadata_score": 0.5,
                "artifact_score": 0.9,
            },
            {
                "model_score": 0.2,
                "metadata_score": 0.25,
                "artifact_score": 0.55,
            },
        )
        self.assertAlmostEqual(score, 0.775)


class DetectionHeuristicTests(SimpleTestCase):
    def setUp(self):
        self.orchestrator = DetectionOrchestrator()

    def test_image_metadata_camera_tags_reduce_ai_score(self):
        score, notes = self.orchestrator._score_image_metadata(
            {
                "image_format": "JPEG",
                "Make": "Canon",
                "Model": "EOS R50",
                "ExposureTime": "1/125",
                "FNumber": "2.8",
            }
        )

        self.assertLess(score, 0.2)
        self.assertTrue(any("Camera acquisition metadata" in note for note in notes))

    def test_image_metadata_ai_keyword_increases_ai_score(self):
        score, notes = self.orchestrator._score_image_metadata(
            {
                "image_format": "PNG",
                "Software": "Midjourney export pipeline",
            }
        )

        self.assertGreater(score, 0.95)
        self.assertTrue(any("AI generation" in note for note in notes))

    def test_image_artifact_scoring_favors_camera_like_statistics(self):
        score, notes = self.orchestrator._score_image_artifacts(
            {
                "edge_density": 0.011,
                "local_noise": 0.0012,
                "detail_residual": 0.003,
                "saturation": 0.18,
                "saturation_spread": 0.11,
                "contrast": 0.28,
                "entropy": 7.4,
                "shadow_clip": 0.0005,
                "highlight_clip": 0.001,
                "histogram_fill": 0.94,
                "saturation_histogram_fill": 0.72,
            }
        )

        self.assertLess(score, 0.25)
        self.assertTrue(any("photographic" in note or "camera" in note for note in notes))

    def test_image_artifact_scoring_flags_synthetic_like_statistics(self):
        score, notes = self.orchestrator._score_image_artifacts(
            {
                "edge_density": 0.031,
                "local_noise": 0.008,
                "detail_residual": 0.009,
                "saturation": 0.22,
                "saturation_spread": 0.24,
                "contrast": 0.26,
                "entropy": 7.75,
                "shadow_clip": 0.018,
                "highlight_clip": 0.021,
                "histogram_fill": 0.99,
                "saturation_histogram_fill": 0.98,
            }
        )

        self.assertGreater(score, 0.8)
        self.assertTrue(any("synthetic" in note or "rendered" in note for note in notes))

    def test_video_temporal_scoring_penalizes_flicker(self):
        stable_score, _ = self.orchestrator._score_video_temporal_artifacts(
            [
                {
                    "edge_density": 0.02,
                    "local_noise": 0.003,
                    "detail_residual": 0.004,
                    "saturation": 0.18,
                    "contrast": 0.22,
                },
                {
                    "edge_density": 0.021,
                    "local_noise": 0.0032,
                    "detail_residual": 0.0041,
                    "saturation": 0.181,
                    "contrast": 0.221,
                },
                {
                    "edge_density": 0.0205,
                    "local_noise": 0.0031,
                    "detail_residual": 0.0042,
                    "saturation": 0.179,
                    "contrast": 0.219,
                },
            ],
            [0.22, 0.24, 0.23],
        )
        flicker_score, _ = self.orchestrator._score_video_temporal_artifacts(
            [
                {
                    "edge_density": 0.01,
                    "local_noise": 0.001,
                    "detail_residual": 0.002,
                    "saturation": 0.11,
                    "contrast": 0.16,
                },
                {
                    "edge_density": 0.05,
                    "local_noise": 0.015,
                    "detail_residual": 0.018,
                    "saturation": 0.33,
                    "contrast": 0.29,
                },
                {
                    "edge_density": 0.018,
                    "local_noise": 0.002,
                    "detail_residual": 0.003,
                    "saturation": 0.12,
                    "contrast": 0.17,
                },
            ],
            [0.2, 0.68, 0.31],
        )

        self.assertLess(stable_score, flicker_score)
