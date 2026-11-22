"""Locked evaluation harness for the route optimization RSI example."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from rsi_demo.evaluator import CaseFailure, EvaluationReport


@dataclass(frozen=True)
class RouteBenchmarkCase:
    """Single locked 2D delivery-tour benchmark case."""

    case_id: str
    tags: tuple[str, ...]
    stops: tuple[tuple[str, float, float], ...]
    optimal_distance: float


ROUTE_BENCHMARK_CASES: tuple[RouteBenchmarkCase, ...] = (
    RouteBenchmarkCase(
        case_id="scrambled_square",
        tags=("geometry", "crossing"),
        stops=(
            ("depot", 0.0, 0.0),
            ("s1", 10.0, 10.0),
            ("s2", 0.0, 10.0),
            ("s3", 10.0, 0.0),
        ),
        optimal_distance=40.0,
    ),
    RouteBenchmarkCase(
        case_id="two_clusters_zigzag",
        tags=("clustering", "nearest_neighbor"),
        stops=(
            ("depot", 0.0, 0.0),
            ("far_a", 50.0, 0.0),
            ("near_a", 2.0, 1.0),
            ("far_b", 52.0, 1.0),
            ("near_b", 1.0, 3.0),
            ("far_c", 51.0, 3.0),
        ),
        optimal_distance=107.880897,
    ),
    RouteBenchmarkCase(
        case_id="figure_eight_crossing",
        tags=("crossing", "two_opt"),
        stops=(
            ("depot", 0.0, 0.0),
            ("a", 1.0, 0.0),
            ("b", 4.0, 3.0),
            ("c", 5.0, 3.0),
            ("d", 5.0, 0.0),
            ("e", 1.0, 3.0),
        ),
        optimal_distance=15.162278,
    ),
    RouteBenchmarkCase(
        case_id="hexagon_shuffled",
        tags=("geometry", "nearest_neighbor"),
        stops=(
            ("depot", 10.0, 0.0),
            ("h3", -10.0, 0.0),
            ("h1", 5.0, 8.660254),
            ("h4", -5.0, -8.660254),
            ("h2", -5.0, 8.660254),
            ("h5", 5.0, -8.660254),
        ),
        optimal_distance=60.0,
    ),
    RouteBenchmarkCase(
        case_id="corridor_detour",
        tags=("nearest_neighbor", "two_opt"),
        stops=(
            ("depot", 0.0, 0.0),
            ("c1", 20.0, 0.0),
            ("c2", 5.0, 1.0),
            ("c3", 15.0, 0.0),
            ("c4", 10.0, 1.0),
            ("c5", 20.0, 4.0),
            ("c6", 0.0, 4.0),
        ),
        optimal_distance=48.198039,
    ),
    RouteBenchmarkCase(
        case_id="grid_eight_stops",
        tags=("geometry", "two_opt"),
        stops=(
            ("depot", 0.0, 0.0),
            ("g1", 6.0, 4.0),
            ("g2", 2.0, 0.0),
            ("g3", 4.0, 4.0),
            ("g4", 6.0, 0.0),
            ("g5", 0.0, 4.0),
            ("g6", 4.0, 0.0),
            ("g7", 2.0, 4.0),
        ),
        optimal_distance=20.0,
    ),
)


def compute_tour_distance(
    stops: tuple[tuple[str, float, float], ...],
    route: list[str],
) -> float:
    """Compute closed-loop Euclidean tour distance for a valid route."""
    coord_map = {stop_id: (x, y) for stop_id, x, y in stops}
    total = 0.0
    for idx, stop_id in enumerate(route):
        x1, y1 = coord_map[stop_id]
        x2, y2 = coord_map[route[(idx + 1) % len(route)]]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def score_route(case: RouteBenchmarkCase, route: object) -> tuple[float, str | None]:
    """Return (score in [0.0, 1.0], error_or_none)."""
    if not isinstance(route, list) or not all(isinstance(x, str) for x in route):
        return 0.0, "Route must be a list of stop ID strings."
    expected_ids = [s[0] for s in case.stops]
    if len(route) != len(expected_ids) or set(route) != set(expected_ids):
        return 0.0, "Route must visit every stop exactly once."
    if route[0] != expected_ids[0]:
        return 0.0, f"Route must start at '{expected_ids[0]}'."

    dist = compute_tour_distance(case.stops, route)
    if dist <= 0.0:
        return 1.0, None
    ratio = min(1.0, case.optimal_distance / dist)
    return round(ratio, 6), None


def _run_route_unit_tests(project_root: Path) -> tuple[int, int, list[str]]:
    tests_dir = project_root / "tests"
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(tests_dir), pattern="test_route_solver.py")
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        runner = unittest.TextTestRunner(stream=devnull, verbosity=0)
        result = runner.run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = max(0, total - failed)
    errors = [
        f"{test}: {trace.strip().splitlines()[-1]}"
        for test, trace in (result.failures + result.errors)
    ]
    return passed, total, errors


def evaluate_route_in_process(
    project_root: Path,
    latency_repeats: int = 10,
) -> EvaluationReport:
    """Evaluate `rsi_demo.route_solver` in the active process."""
    src_dir = str((project_root / "src").resolve())
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from rsi_demo import route_solver as solver_mod  # noqa: PLC0415

    solver_version = str(getattr(solver_mod, "SOLVER_VERSION", "unknown"))
    plan_fn = solver_mod.plan_route

    case_scores: list[float] = []
    latencies_ms: list[float] = []
    failures: list[CaseFailure] = []
    cases_passed = 0

    for case in ROUTE_BENCHMARK_CASES:
        actual: list[str] | None = None
        err: str | None = None
        start = time.perf_counter()
        try:
            for _ in range(max(1, latency_repeats)):
                actual = plan_fn(list(case.stops))
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        elapsed_ms = ((time.perf_counter() - start) * 1000.0) / max(1, latency_repeats)
        latencies_ms.append(elapsed_ms)

        if err is not None:
            case_score = 0.0
        else:
            case_score, err = score_route(case, actual)

        case_scores.append(case_score)
        if case_score >= 0.99:
            cases_passed += 1
        else:
            dist = (
                compute_tour_distance(case.stops, actual)
                if err is None and isinstance(actual, list)
                else None
            )
            failures.append(
                CaseFailure(
                    case_id=case.case_id,
                    tags=list(case.tags),
                    input_text=f"{len(case.stops)} stops (optimal={case.optimal_distance:.2f})",
                    expected={"optimal_distance": case.optimal_distance},
                    actual={"route": actual, "distance": round(dist, 3) if dist else None},
                    score=case_score,
                    error=err,
                )
            )

    ut_passed, ut_total, ut_errors = _run_route_unit_tests(project_root)
    ut_pass_rate = (ut_passed / ut_total) if ut_total > 0 else 0.0

    total_cases = len(ROUTE_BENCHMARK_CASES)
    accuracy = sum(case_scores) / total_cases
    case_pass_rate = cases_passed / total_cases
    sorted_lat = sorted(latencies_ms)
    p95_idx = min(len(sorted_lat) - 1, int(0.95 * (len(sorted_lat) - 1)))
    avg_latency_ms = sum(latencies_ms) / len(latencies_ms)
    p95_latency_ms = sorted_lat[p95_idx]
    composite_score = round(0.85 * accuracy + 0.15 * case_pass_rate, 6)

    return EvaluationReport(
        solver_version=solver_version,
        accuracy=round(accuracy, 6),
        case_pass_rate=round(case_pass_rate, 6),
        cases_passed=cases_passed,
        total_cases=total_cases,
        unit_test_pass_rate=round(ut_pass_rate, 6),
        unit_tests_passed=ut_passed,
        unit_tests_total=ut_total,
        avg_latency_ms=round(avg_latency_ms, 4),
        p95_latency_ms=round(p95_latency_ms, 4),
        composite_score=composite_score,
        failures=failures,
        unit_test_errors=ut_errors,
    )


def evaluate_route_sandboxed(
    project_root: Path,
    timeout_seconds: float = 10.0,
) -> EvaluationReport:
    """Run route evaluation in a fresh isolated subprocess with timeout protection."""
    root = Path(project_root).resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = str((root / "src").resolve())

    proc = subprocess.run(
        [sys.executable, "-m", "rsi_demo.route_evaluator", "--worker", str(root)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Route evaluation subprocess failed (code {proc.returncode}): {proc.stderr.strip()}"
        )
    payload = json.loads(proc.stdout)
    failures = [CaseFailure(**item) for item in payload.pop("failures", [])]
    return EvaluationReport(failures=failures, **payload)


def _main_worker() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        root = Path(sys.argv[2]).resolve()
        report = evaluate_route_in_process(root)
        print(json.dumps(report.to_dict()))
        return 0
    print("Usage: python -m rsi_demo.route_evaluator --worker <project_root>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main_worker())
