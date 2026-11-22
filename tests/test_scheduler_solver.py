"""Locked contract unit tests for `rsi_demo.scheduler_solver`."""

from __future__ import annotations

import unittest

from rsi_demo.scheduler_solver import plan_schedule


class TestSchedulerSolverContract(unittest.TestCase):
    """Core invariants every scheduler version must uphold."""

    def test_empty_jobs_returns_empty_list(self) -> None:
        self.assertEqual(plan_schedule([]), [])

    def test_single_job_returns_single_job(self) -> None:
        self.assertEqual(plan_schedule([("task_a", 2.0, 5.0)]), ["task_a"])

    def test_schedules_every_job_exactly_once(self) -> None:
        jobs = [
            ("long", 8.0, 4.0),
            ("short_1", 1.0, 2.0),
            ("short_2", 2.0, 5.0),
        ]
        order = plan_schedule(jobs)
        self.assertEqual(len(order), len(jobs))
        self.assertEqual(set(order), {"long", "short_1", "short_2"})

    def test_returns_list_of_strings(self) -> None:
        order = plan_schedule([("a", 1.0, 3.0), ("b", 2.0, 4.0)])
        self.assertIsInstance(order, list)
        self.assertTrue(all(isinstance(item, str) for item in order))


if __name__ == "__main__":
    unittest.main()
