"""Offline deterministic proposer for the 2D route optimization RSI example."""

from __future__ import annotations

from typing import Any

from rsi_demo.evaluator import EvaluationReport
from rsi_demo.proposer import Proposal


_ROUTE_V1_NN = '''"""Active route-optimization solver iteratively improved during RSI cycles."""

from __future__ import annotations

import math
from typing import Sequence

SOLVER_VERSION = "v1-nearest-neighbor"


def plan_route(stops: Sequence[tuple[str, float, float]]) -> list[str]:
    """Greedy nearest-neighbor tour starting at `stops[0]`."""
    if not stops:
        return []
    remaining = list(stops[1:])
    route = [stops[0][0]]
    cur_x, cur_y = stops[0][1], stops[0][2]

    while remaining:
        best_idx = min(
            range(len(remaining)),
            key=lambda i: math.hypot(remaining[i][1] - cur_x, remaining[i][2] - cur_y),
        )
        nxt_id, cur_x, cur_y = remaining.pop(best_idx)
        route.append(nxt_id)
    return route
'''


_ROUTE_V2_TWO_OPT = '''"""Active route-optimization solver iteratively improved during RSI cycles."""

from __future__ import annotations

import math
from typing import Sequence

SOLVER_VERSION = "v2-two-opt"


def _dist(a: tuple[str, float, float], b: tuple[str, float, float]) -> float:
    return math.hypot(b[1] - a[1], b[2] - a[2])


def _two_opt(tour: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    n = len(tour)
    if n < 4:
        return tour
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = tour[i - 1], tour[i]
                c, d = tour[j], tour[(j + 1) % n]
                if _dist(a, c) + _dist(b, d) + 1e-9 < _dist(a, b) + _dist(c, d):
                    tour[i : j + 1] = reversed(tour[i : j + 1])
                    improved = True
    return tour


def plan_route(stops: Sequence[tuple[str, float, float]]) -> list[str]:
    """Nearest-neighbor seed followed by 2-opt edge uncrossing."""
    if not stops:
        return []
    remaining = list(stops[1:])
    tour = [stops[0]]
    cur_x, cur_y = stops[0][1], stops[0][2]

    while remaining:
        best_idx = min(
            range(len(remaining)),
            key=lambda i: math.hypot(remaining[i][1] - cur_x, remaining[i][2] - cur_y),
        )
        nxt = remaining.pop(best_idx)
        tour.append(nxt)
        cur_x, cur_y = nxt[1], nxt[2]

    tour = _two_opt(tour)
    return [stop[0] for stop in tour]
'''


_ROUTE_V3_REGRESSION = '''"""Active route-optimization solver iteratively improved during RSI cycles."""

from __future__ import annotations

from typing import Sequence

SOLVER_VERSION = "v3-x-sort-regression"


def plan_route(stops: Sequence[tuple[str, float, float]]) -> list[str]:
    """Flawed shortcut: sorts all stops by X coordinate, breaking depot-start invariant."""
    if not stops:
        return []
    return [stop[0] for stop in sorted(stops, key=lambda s: (s[1], s[2]))]
'''


_ROUTE_V3_MULTISTART = '''"""Active route-optimization solver iteratively improved during RSI cycles."""

from __future__ import annotations

import math
from typing import Sequence

SOLVER_VERSION = "v3-multistart-two-opt"


def _dist(a: tuple[str, float, float], b: tuple[str, float, float]) -> float:
    return math.hypot(b[1] - a[1], b[2] - a[2])


def _tour_length(tour: list[tuple[str, float, float]]) -> float:
    n = len(tour)
    return sum(_dist(tour[i], tour[(i + 1) % n]) for i in range(n))


def _two_opt(tour: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    n = len(tour)
    if n < 4:
        return tour
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = tour[i - 1], tour[i]
                c, d = tour[j], tour[(j + 1) % n]
                if _dist(a, c) + _dist(b, d) + 1e-9 < _dist(a, b) + _dist(c, d):
                    tour[i : j + 1] = reversed(tour[i : j + 1])
                    improved = True
    return tour


def _nearest_neighbor(stops: Sequence[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    remaining = list(stops[1:])
    tour = [stops[0]]
    cur = stops[0]
    while remaining:
        best_idx = min(range(len(remaining)), key=lambda i: _dist(cur, remaining[i]))
        cur = remaining.pop(best_idx)
        tour.append(cur)
    return tour


def _polar_angle_seed(stops: Sequence[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    cx = sum(s[1] for s in stops) / len(stops)
    cy = sum(s[2] for s in stops) / len(stops)
    rest = sorted(stops[1:], key=lambda s: math.atan2(s[2] - cy, s[1] - cx))
    return [stops[0], *rest]


def plan_route(stops: Sequence[tuple[str, float, float]]) -> list[str]:
    """Multi-seed 2-opt tour optimizer preserving `stops[0]` as start."""
    if not stops:
        return []
    candidates = [
        _two_opt(list(stops)),
        _two_opt(_nearest_neighbor(stops)),
        _two_opt(_polar_angle_seed(stops)),
    ]
    best = min(candidates, key=_tour_length)
    return [stop[0] for stop in best]
'''


_ROUTE_V4_PLATEAU = _ROUTE_V3_MULTISTART.replace(
    'SOLVER_VERSION = "v3-multistart-two-opt"',
    'SOLVER_VERSION = "v4-plateau-noop"',
)


class RouteMockProposer:
    """Offline deterministic proposer for route optimization."""

    name = "mock-route-offline"

    def __init__(self, include_regression_demo: bool = True) -> None:
        self.include_regression_demo = include_regression_demo

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict[str, Any]],
    ) -> Proposal:
        tried = {entry.get("proposed_version") for entry in history}

        if "v1-nearest-neighbor" not in tried:
            return Proposal(
                version_label="v1-nearest-neighbor",
                hypothesis="Replace naive input order with greedy nearest-neighbor selection.",
                rationale=(
                    f"Input-order baseline fails on {len(report.failures)}/{report.total_cases} "
                    "tours due to cross-cluster zigzags."
                ),
                target_failure_tags=("clustering", "nearest_neighbor"),
                candidate_source=_ROUTE_V1_NN,
            )

        if "v2-two-opt" not in tried:
            return Proposal(
                version_label="v2-two-opt",
                hypothesis="Apply 2-opt edge uncrossing on top of nearest-neighbor tour.",
                rationale="Nearest-neighbor leaves crossing edges on figure-8 and corridor cases.",
                target_failure_tags=("crossing", "two_opt"),
                candidate_source=_ROUTE_V2_TWO_OPT,
            )

        if self.include_regression_demo and "v3-x-sort-regression" not in tried:
            return Proposal(
                version_label="v3-x-sort-regression",
                hypothesis="Sort stops directly by X coordinate for fast sweep ordering.",
                rationale="Attempting a simpler coordinate sort instead of multi-pass local search.",
                target_failure_tags=("geometry",),
                candidate_source=_ROUTE_V3_REGRESSION,
            )

        if "v3-multistart-two-opt" not in tried:
            return Proposal(
                version_label="v3-multistart-two-opt",
                hypothesis="Run 2-opt from multiple geometric seeds (NN, polar angle, input) and pick best.",
                rationale=(
                    "Previous X-sort violated the depot-start contract; multi-seed 2-opt "
                    "escapes single-seed local minima safely."
                ),
                target_failure_tags=("crossing", "two_opt", "geometry"),
                candidate_source=_ROUTE_V3_MULTISTART,
            )

        return Proposal(
            version_label="v4-plateau-noop",
            hypothesis="Attempt minor version bump at convergence plateau.",
            rationale="Tours already match or nearly match optimal distance.",
            target_failure_tags=(),
            candidate_source=_ROUTE_V4_PLATEAU,
        )
