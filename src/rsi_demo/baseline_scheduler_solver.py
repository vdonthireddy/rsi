"""Immutable v0 baseline solver for deadline-aware job scheduling.

Locked during RSI runs and used to initialize/reset `scheduler_solver.py`.
"""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v0-input-order"


def plan_schedule(jobs: Sequence[tuple[str, float, float]]) -> list[str]:
    """Return a single-machine execution order for `(job_id, duration, deadline)`.

    Baseline strategy (v0): run jobs in the exact input order given.
    """
    if not jobs:
        return []
    return [job_id for job_id, _, _ in jobs]
