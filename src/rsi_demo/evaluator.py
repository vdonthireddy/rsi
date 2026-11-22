"""Locked evaluation harness and benchmark suite for the RSI demo.

This module is integrity-checked before and after every RSI cycle.
It runs candidate solvers inside a fresh subprocess with a wall-clock timeout
to prevent module caching issues, infinite loops, or state leakage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import unittest


@dataclass(frozen=True)
class BenchmarkCase:
    """Single locked evaluation case."""

    case_id: str
    tags: tuple[str, ...]
    input_text: str
    expected: dict[str, Any]


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="clean_json",
        tags=("json",),
        input_text='{"name": "Alice", "age": 30, "active": true}',
        expected={"name": "Alice", "age": 30, "active": True},
    ),
    BenchmarkCase(
        case_id="fenced_json_with_prose",
        tags=("fenced_json", "prose_wrapper"),
        input_text=(
            "Here is the extracted record:\n"
            "```json\n"
            '{"id": 101, "status": "ok", "verified": false}\n'
            "```\n"
            "End of response."
        ),
        expected={"id": 101, "status": "ok", "verified": False},
    ),
    BenchmarkCase(
        case_id="embedded_json_trailing_comma",
        tags=("embedded_json", "trailing_comma"),
        input_text='Result => {"item": "widget", "count": 3, "in_stock": true,}',
        expected={"item": "widget", "count": 3, "in_stock": True},
    ),
    BenchmarkCase(
        case_id="json_with_noise_prefix",
        tags=("embedded_json", "prose_wrapper"),
        input_text='INFO 2026: payload={"user": "sam", "score": 98.5, "passed": true}',
        expected={"user": "sam", "score": 98.5, "passed": True},
    ),
    BenchmarkCase(
        case_id="quoted_json_string_fields",
        tags=("json", "quoted_delimiters"),
        input_text='{"note": "a: b, c", "ok": true, "err": null}',
        expected={"note": "a: b, c", "ok": True, "err": None},
    ),
    BenchmarkCase(
        case_id="kv_multiline_typed",
        tags=("kv_multiline", "type_coercion"),
        input_text="name: Bob\nrole: engineer\nlevel: 4\nactive: true",
        expected={"name": "Bob", "role": "engineer", "level": 4, "active": True},
    ),
    BenchmarkCase(
        case_id="kv_inline_semicolon",
        tags=("kv_inline", "equals_delimiter", "type_coercion"),
        input_text="host=db01; port=5432; tls=true; timeout=null",
        expected={"host": "db01", "port": 5432, "tls": True, "timeout": None},
    ),
    BenchmarkCase(
        case_id="kv_inline_comma",
        tags=("kv_inline", "type_coercion"),
        input_text="city: Austin, temp: 72.5, sunny: false",
        expected={"city": "Austin", "temp": 72.5, "sunny": False},
    ),
    BenchmarkCase(
        case_id="comments_and_banners",
        tags=("comments_banners", "type_coercion"),
        input_text="# Auto-generated\n--- RECORD ---\nenv: prod\nreplicas: 3\n\n# end",
        expected={"env": "prod", "replicas": 3},
    ),
    BenchmarkCase(
        case_id="negative_and_zero",
        tags=("type_coercion", "negative_numbers"),
        input_text="delta: -12.5\nretries: 0\nflag: off",
        expected={"delta": -12.5, "retries": 0, "flag": False},
    ),
    BenchmarkCase(
        case_id="mixed_equals_and_colons",
        tags=("kv_inline", "equals_delimiter", "currency", "type_coercion"),
        input_text="region=us-west, tier: gold, discount: $10, active: yes",
        expected={"region": "us-west", "tier": "gold", "discount": 10, "active": True},
    ),
    BenchmarkCase(
        case_id="url_and_timestamp_colons",
        tags=("colons_in_values",),
        input_text=(
            "service: auth\n"
            "endpoint: https://api.example.com:8443/v1\n"
            "updated_at: 2026-03-10T14:22:00Z"
        ),
        expected={
            "service": "auth",
            "endpoint": "https://api.example.com:8443/v1",
            "updated_at": "2026-03-10T14:22:00Z",
        },
    ),
    BenchmarkCase(
        case_id="quoted_delimiters",
        tags=("quoted_delimiters", "kv_inline", "type_coercion"),
        input_text='title: "Alert: disk full, node 3", severity: "high", retries: 2',
        expected={"title": "Alert: disk full, node 3", "severity": "high", "retries": 2},
    ),
    BenchmarkCase(
        case_id="aliases_and_casing",
        tags=("key_aliases", "currency", "type_coercion"),
        input_text="User_Email: ADA@EXAMPLE.COM\nQty: 7\nAmt: $49.50",
        expected={"email": "ADA@EXAMPLE.COM", "quantity": 7, "amount": 49.5},
    ),
    BenchmarkCase(
        case_id="unstructured_graceful_empty",
        tags=("edge_case",),
        input_text="Nothing useful here at all.",
        expected={},
    ),
)


@dataclass(frozen=True)
class CaseFailure:
    """Detailed failure record for proposer inspection."""

    case_id: str
    tags: list[str]
    input_text: str
    expected: dict[str, Any]
    actual: dict[str, Any] | None
    score: float
    error: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    """Complete metrics produced by evaluating a solver against locked checks."""

    solver_version: str
    accuracy: float
    case_pass_rate: float
    cases_passed: int
    total_cases: int
    unit_test_pass_rate: float
    unit_tests_passed: int
    unit_tests_total: int
    avg_latency_ms: float
    p95_latency_ms: float
    composite_score: float
    failures: list[CaseFailure]
    unit_test_errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _typed_items(record: dict[str, Any]) -> set[tuple[str, str, Any]]:
    """Convert dict items into type-tagged tuples so True != 1 and '4' != 4."""
    items: set[tuple[str, str, Any]] = set()
    for k, v in record.items():
        # Convert nested dicts/lists deterministically via JSON if present.
        if isinstance(v, (dict, list)):
            norm_v: Any = json.dumps(v, sort_keys=True)
        else:
            norm_v = v
        items.add((str(k), type(v).__name__, norm_v))
    return items


def score_case(expected: dict[str, Any], actual: Any) -> float:
    """Compute strict, type-aware F1 score between expected and actual records."""
    if not isinstance(actual, dict):
        return 0.0
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0

    exp_items = _typed_items(expected)
    act_items = _typed_items(actual)
    overlap = len(exp_items & act_items)
    if overlap == 0:
        return 0.0
    precision = overlap / len(act_items)
    recall = overlap / len(exp_items)
    return round(2 * precision * recall / (precision + recall), 6)


def _run_solver_unit_tests(project_root: Path) -> tuple[int, int, list[str]]:
    """Run the locked solver contract unit tests via stdlib unittest."""
    tests_dir = project_root / "tests"
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(tests_dir), pattern="test_solver.py")
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


def evaluate_in_process(
    project_root: Path,
    latency_repeats: int = 10,
) -> EvaluationReport:
    """Evaluate the currently on-disk `rsi_demo.solver` in the active process."""
    src_dir = str((project_root / "src").resolve())
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from rsi_demo import solver as solver_mod  # noqa: PLC0415

    solver_version = str(getattr(solver_mod, "SOLVER_VERSION", "unknown"))
    extract_fn = solver_mod.extract_record

    case_scores: list[float] = []
    latencies_ms: list[float] = []
    failures: list[CaseFailure] = []
    cases_passed = 0

    for case in BENCHMARK_CASES:
        actual: dict[str, Any] | None = None
        err: str | None = None
        start = time.perf_counter()
        try:
            for _ in range(max(1, latency_repeats)):
                actual = extract_fn(case.input_text)
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        elapsed_ms = ((time.perf_counter() - start) * 1000.0) / max(1, latency_repeats)
        latencies_ms.append(elapsed_ms)

        if err is not None:
            case_score = 0.0
        else:
            case_score = score_case(case.expected, actual)

        case_scores.append(case_score)
        if case_score == 1.0:
            cases_passed += 1
        else:
            failures.append(
                CaseFailure(
                    case_id=case.case_id,
                    tags=list(case.tags),
                    input_text=case.input_text,
                    expected=case.expected,
                    actual=actual if isinstance(actual, dict) else None,
                    score=case_score,
                    error=err,
                )
            )

    ut_passed, ut_total, ut_errors = _run_solver_unit_tests(project_root)
    ut_pass_rate = (ut_passed / ut_total) if ut_total > 0 else 0.0

    total_cases = len(BENCHMARK_CASES)
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


def evaluate_sandboxed(
    project_root: Path,
    timeout_seconds: float = 10.0,
) -> EvaluationReport:
    """Run evaluation in a fresh isolated subprocess with timeout protection."""
    root = Path(project_root).resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = str((root / "src").resolve())

    proc = subprocess.run(
        [sys.executable, "-m", "rsi_demo.evaluator", "--worker", str(root)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Evaluation subprocess failed (code {proc.returncode}): {proc.stderr.strip()}"
        )
    payload = json.loads(proc.stdout)
    failures = [CaseFailure(**item) for item in payload.pop("failures", [])]
    return EvaluationReport(failures=failures, **payload)


def _main_worker() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        root = Path(sys.argv[2]).resolve()
        report = evaluate_in_process(root)
        print(json.dumps(report.to_dict()))
        return 0
    print("Usage: python -m rsi_demo.evaluator --worker <project_root>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main_worker())
