from __future__ import annotations

import unittest

from study.scoring import score_office, score_search_recon


class ScoringTests(unittest.TestCase):
    def test_office_valid_delivery(self):
        path = [(8, 4), (8, 5), (8, 6), (8, 7), (7, 7), (6, 7), (5, 7), (4, 7),
                (5, 7), (6, 7), (7, 7), (7, 6), (7, 5), (7, 4)]
        result = score_office(path)
        self.assertTrue(result.valid)
        self.assertTrue(result.completed)
        self.assertEqual(result.details["picked_from"], [4, 7])

    def test_search_hidden_high_is_flagged(self):
        path = [(10, 5), (9, 5), (8, 5)]
        result = score_search_recon(path)
        self.assertTrue(result.valid)
        self.assertTrue(result.hidden_hazard_entered)
        self.assertTrue(result.details["stuck"])

    def test_search_complete_route_is_accepted_even_if_high_debris_is_entered(self):
        # This route is intentionally synthetic. It visits every target,
        # returns home, and crosses the hidden HIGH cell at (8, 5). The route
        # must be accepted for the user study while execution_success is false.
        path = [
            (10, 5), (9, 5), (8, 5), (8, 4), (8, 3), (8, 2),
            (9, 2), (9, 1), (8, 1), (8, 0), (7, 0), (6, 0),
            (5, 0), (4, 0), (3, 0), (2, 0), (1, 0), (1, 1),
            (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6),
            (0, 7), (0, 8), (1, 8), (1, 9), (2, 9), (2, 8),
            (3, 8), (4, 8), (5, 8), (6, 8), (7, 8), (8, 8),
            (9, 8), (9, 9), (10, 9), (10, 8), (10, 7), (10, 6),
            (10, 5),
        ]
        result = score_search_recon(path)
        self.assertTrue(result.valid)
        self.assertTrue(result.completed)
        self.assertTrue(result.details["route_completed"])
        self.assertFalse(result.details["execution_success"])
        self.assertTrue(result.hidden_hazard_entered)


if __name__ == "__main__":
    unittest.main()
