"""Core Recursive Self-Improvement (RSI) orchestrator loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from rsi_demo.evaluator import EvaluationReport, evaluate_sandboxed
from rsi_demo.guardrails import (
    HARD_MAX_CYCLES,
    GuardrailViolation,
    LockedFileManifest,
    SandboxPaths,
    check_candidate_acceptance,
    validate_candidate_ast,
    validate_max_cycles,
)
from rsi_demo.proposer import MockProposer, Proposer


@dataclass(frozen=True)
class CycleRecord:
    """Deterministic audit record for one RSI improvement cycle."""

    cycle: int
    proposer: str
    base_version: str
    proposed_version: str
    hypothesis: str
    rationale: str
    target_failure_tags: list[str]
    ast_check_passed: bool
    ast_error: str | None
    candidate_sha256: str
    decision: str  # "accepted" | "rolled_back"
    decision_reason: str
    before_score: float
    after_score: float | None
    before_accuracy: float
    after_accuracy: float | None
    cases_passed: str | None
    unit_tests_passed: str | None
    avg_latency_ms: float | None


@dataclass(frozen=True)
class RunSummary:
    """End-of-run summary across all RSI cycles."""

    run_id: str
    proposer: str
    max_cycles: int
    cycles_executed: int
    baseline_version: str
    final_version: str
    baseline_score: float
    final_score: float
    baseline_accuracy: float
    final_accuracy: float
    accepted_cycles: int
    rolled_back_cycles: int
    locked_manifest_hashes: dict[str, str]
    cycles: list[CycleRecord]
    run_dir: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run_rsi_loop(
    project_root: Path | str,
    max_cycles: int = HARD_MAX_CYCLES,
    proposer: Proposer | None = None,
    run_id: str = "run-offline-default",
    reset_to_baseline: bool = True,
    eval_timeout_seconds: float = 10.0,
) -> RunSummary:
    """Execute a bounded, integrity-checked RSI loop inside `project_root`."""
    validated_cycles = validate_max_cycles(max_cycles)
    paths = SandboxPaths.from_project_root(project_root)
    manifest = LockedFileManifest(paths.locked_files())
    active_proposer: Proposer = proposer if proposer is not None else MockProposer()

    run_dir = paths.ensure_mutable_target(paths.runs_dir / run_id)
    versions_dir = paths.ensure_mutable_target(run_dir / "versions")
    versions_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.ensure_mutable_target(run_dir / "cycles.jsonl")
    summary_path = paths.ensure_mutable_target(run_dir / "summary.json")

    manifest.verify()

    if reset_to_baseline:
        baseline_source = paths.baseline_path.read_text(encoding="utf-8")
        paths.ensure_mutable_target(paths.solver_path).write_text(
            baseline_source, encoding="utf-8"
        )

    best_source = paths.solver_path.read_text(encoding="utf-8")
    validate_candidate_ast(best_source)
    best_report: EvaluationReport = evaluate_sandboxed(
        paths.project_root, timeout_seconds=eval_timeout_seconds
    )
    manifest.verify()

    baseline_report = best_report
    (versions_dir / "00_baseline_solver.py").write_text(best_source, encoding="utf-8")
    log_lines: list[str] = []
    history: list[dict[str, Any]] = []
    cycles: list[CycleRecord] = []
    accepted_count = 0
    rolled_back_count = 0

    for cycle in range(1, validated_cycles + 1):
        manifest.verify()
        proposal = active_proposer.propose(
            cycle=cycle,
            current_source=best_source,
            report=best_report,
            history=history,
        )
        candidate_hash = _sha256_text(proposal.candidate_source)

        ast_passed = True
        ast_error: str | None = None
        try:
            validate_candidate_ast(proposal.candidate_source)
        except GuardrailViolation as exc:
            ast_passed = False
            ast_error = str(exc)

        if not ast_passed:
            rolled_back_count += 1
            (versions_dir / f"{cycle:02d}_rejected_ast_{proposal.version_label}.py").write_text(
                proposal.candidate_source, encoding="utf-8"
            )
            record = CycleRecord(
                cycle=cycle,
                proposer=active_proposer.name,
                base_version=best_report.solver_version,
                proposed_version=proposal.version_label,
                hypothesis=proposal.hypothesis,
                rationale=proposal.rationale,
                target_failure_tags=list(proposal.target_failure_tags),
                ast_check_passed=False,
                ast_error=ast_error,
                candidate_sha256=candidate_hash,
                decision="rolled_back",
                decision_reason=f"AST safety check failed before execution: {ast_error}",
                before_score=best_report.composite_score,
                after_score=None,
                before_accuracy=best_report.accuracy,
                after_accuracy=None,
                cases_passed=None,
                unit_tests_passed=None,
                avg_latency_ms=None,
            )
            cycles.append(record)
            rec_dict = asdict(record)
            history.append(rec_dict)
            log_lines.append(json.dumps(rec_dict, sort_keys=True))
            continue

        # Write candidate inside sandbox and evaluate in an isolated subprocess.
        paths.ensure_mutable_target(paths.solver_path).write_text(
            proposal.candidate_source, encoding="utf-8"
        )
        candidate_report: EvaluationReport | None = None
        eval_error: str | None = None
        try:
            candidate_report = evaluate_sandboxed(
                paths.project_root, timeout_seconds=eval_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001
            eval_error = f"{type(exc).__name__}: {exc}"
        finally:
            manifest.verify()

        if candidate_report is None:
            # Roll back immediately on crash or timeout.
            paths.ensure_mutable_target(paths.solver_path).write_text(
                best_source, encoding="utf-8"
            )
            rolled_back_count += 1
            (versions_dir / f"{cycle:02d}_rejected_err_{proposal.version_label}.py").write_text(
                proposal.candidate_source, encoding="utf-8"
            )
            record = CycleRecord(
                cycle=cycle,
                proposer=active_proposer.name,
                base_version=best_report.solver_version,
                proposed_version=proposal.version_label,
                hypothesis=proposal.hypothesis,
                rationale=proposal.rationale,
                target_failure_tags=list(proposal.target_failure_tags),
                ast_check_passed=True,
                ast_error=None,
                candidate_sha256=candidate_hash,
                decision="rolled_back",
                decision_reason=f"Candidate evaluation crashed/timed out: {eval_error}; rolled back.",
                before_score=best_report.composite_score,
                after_score=None,
                before_accuracy=best_report.accuracy,
                after_accuracy=None,
                cases_passed=None,
                unit_tests_passed=None,
                avg_latency_ms=None,
            )
            cycles.append(record)
            rec_dict = asdict(record)
            history.append(rec_dict)
            log_lines.append(json.dumps(rec_dict, sort_keys=True))
            continue

        accepted, reason = check_candidate_acceptance(
            best_composite=best_report.composite_score,
            best_accuracy=best_report.accuracy,
            candidate_composite=candidate_report.composite_score,
            candidate_accuracy=candidate_report.accuracy,
            unit_test_pass_rate=candidate_report.unit_test_pass_rate,
            avg_latency_ms=candidate_report.avg_latency_ms,
        )

        if accepted:
            accepted_count += 1
            previous_score = best_report.composite_score
            previous_acc = best_report.accuracy
            previous_ver = best_report.solver_version
            best_source = proposal.candidate_source
            best_report = candidate_report
            (versions_dir / f"{cycle:02d}_accepted_{proposal.version_label}.py").write_text(
                best_source, encoding="utf-8"
            )
            decision = "accepted"
        else:
            rolled_back_count += 1
            previous_score = best_report.composite_score
            previous_acc = best_report.accuracy
            previous_ver = best_report.solver_version
            paths.ensure_mutable_target(paths.solver_path).write_text(
                best_source, encoding="utf-8"
            )
            (versions_dir / f"{cycle:02d}_rolled_back_{proposal.version_label}.py").write_text(
                proposal.candidate_source, encoding="utf-8"
            )
            decision = "rolled_back"

        record = CycleRecord(
            cycle=cycle,
            proposer=active_proposer.name,
            base_version=previous_ver,
            proposed_version=proposal.version_label,
            hypothesis=proposal.hypothesis,
            rationale=proposal.rationale,
            target_failure_tags=list(proposal.target_failure_tags),
            ast_check_passed=True,
            ast_error=None,
            candidate_sha256=candidate_hash,
            decision=decision,
            decision_reason=reason,
            before_score=previous_score,
            after_score=candidate_report.composite_score,
            before_accuracy=previous_acc,
            after_accuracy=candidate_report.accuracy,
            cases_passed=f"{candidate_report.cases_passed}/{candidate_report.total_cases}",
            unit_tests_passed=(
                f"{candidate_report.unit_tests_passed}/{candidate_report.unit_tests_total}"
            ),
            avg_latency_ms=candidate_report.avg_latency_ms,
        )
        cycles.append(record)
        rec_dict = asdict(record)
        history.append(rec_dict)
        log_lines.append(json.dumps(rec_dict, sort_keys=True))

    manifest.verify()
    (versions_dir / "best_solver.py").write_text(best_source, encoding="utf-8")
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    summary = RunSummary(
        run_id=run_id,
        proposer=active_proposer.name,
        max_cycles=validated_cycles,
        cycles_executed=len(cycles),
        baseline_version=baseline_report.solver_version,
        final_version=best_report.solver_version,
        baseline_score=baseline_report.composite_score,
        final_score=best_report.composite_score,
        baseline_accuracy=baseline_report.accuracy,
        final_accuracy=best_report.accuracy,
        accepted_cycles=accepted_count,
        rolled_back_cycles=rolled_back_count,
        locked_manifest_hashes={str(k.relative_to(paths.project_root)): v for k, v in manifest.hashes.items()},
        cycles=cycles,
        run_dir=str(run_dir.relative_to(paths.project_root)),
    )
    summary_path.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
