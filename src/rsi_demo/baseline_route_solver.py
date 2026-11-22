"""Immutable v0 baseline solver for 2D delivery route optimization.

Locked during RSI runs and used to initialize/reset `route_solver.py`.
"""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v0-input-order"


def plan_route(stops: Sequence[tuple[str, float, float]]) -> list[str]:
    """Return a closed-tour visit order starting at `stops[0]`.

    Baseline strategy (v0): visit stops in the exact input order given.
    """
    if not stops:
        return []
    return [stop_id for stop_id, _, _ in stops]
