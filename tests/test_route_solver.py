"""Locked contract unit tests for `rsi_demo.route_solver`."""

from __future__ import annotations

import unittest

from rsi_demo.route_solver import plan_route


class TestRouteSolverContract(unittest.TestCase):
    """Core invariants every route solver version must uphold."""

    def test_empty_stops_returns_empty_list(self) -> None:
        self.assertEqual(plan_route([]), [])

    def test_single_stop_returns_single_stop(self) -> None:
        self.assertEqual(plan_route([("depot", 0.0, 0.0)]), ["depot"])

    def test_starts_at_first_stop_and_visits_all_once(self) -> None:
        stops = [
            ("depot", 0.0, 0.0),
            ("a", 5.0, 0.0),
            ("b", 5.0, 5.0),
            ("c", 0.0, 5.0),
        ]
        route = plan_route(stops)
        self.assertEqual(route[0], "depot")
        self.assertEqual(len(route), len(stops))
        self.assertEqual(set(route), {"depot", "a", "b", "c"})

    def test_starts_at_first_stop_even_when_not_leftmost(self) -> None:
        stops = [
            ("depot", 10.0, 0.0),
            ("west", -5.0, 0.0),
            ("north", 2.0, 5.0),
        ]
        route = plan_route(stops)
        self.assertEqual(route[0], "depot")
        self.assertEqual(set(route), {"depot", "west", "north"})

    def test_returns_list_of_strings(self) -> None:
        route = plan_route([("depot", 1.0, 2.0), ("x", 3.0, 4.0)])
        self.assertIsInstance(route, list)
        self.assertTrue(all(isinstance(item, str) for item in route))


if __name__ == "__main__":
    unittest.main()
