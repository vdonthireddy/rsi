"""Safety sandbox, anti-tamper integrity checks, and acceptance guardrails.

This module is locked during RSI runs. Any modification to this file during
an active run triggers an immediate TamperDetectedError abort.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

HARD_MAX_CYCLES = 5
MAX_AVG_LATENCY_MS = 50.0
MIN_SCORE_IMPROVEMENT = 1e-6

ALLOWED_SOLVER_IMPORTS = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "json",
        "math",
        "re",
        "string",
        "typing",
    }
)

FORBIDDEN_CALL_OR_NAME_NODES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "input",
        "exit",
        "quit",
    }
)

FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__import__",
        "system",
        "popen",
        "spawn",
    }
)


class GuardrailViolation(RuntimeError):
    """Raised when a candidate or configuration violates safety guardrails."""


class TamperDetectedError(GuardrailViolation):
    """Raised when a locked file changes during an RSI run."""


@dataclass(frozen=True)
class SandboxPaths:
    """Resolved, containment-checked paths inside the RSI project directory."""

    project_root: Path
    src_dir: Path
    solver_path: Path
    baseline_path: Path
    evaluator_path: Path
    guardrails_path: Path
    unit_test_path: Path
    tests_dir: Path
    runs_dir: Path

    @classmethod
    def from_project_root(
        cls,
        root: Path | str,
        solver_rel_path: str = "src/rsi_demo/solver.py",
        baseline_rel_path: str = "src/rsi_demo/baseline_solver.py",
        evaluator_rel_path: str = "src/rsi_demo/evaluator.py",
        unit_test_rel_path: str = "tests/test_solver.py",
    ) -> "SandboxPaths":
        project_root = Path(root).resolve()
        src_dir = (project_root / "src" / "rsi_demo").resolve()
        tests_dir = (project_root / "tests").resolve()
        runs_dir = (project_root / "runs").resolve()

        paths = cls(
            project_root=project_root,
            src_dir=src_dir,
            solver_path=(project_root / solver_rel_path).resolve(),
            baseline_path=(project_root / baseline_rel_path).resolve(),
            evaluator_path=(project_root / evaluator_rel_path).resolve(),
            guardrails_path=(src_dir / "guardrails.py").resolve(),
            unit_test_path=(project_root / unit_test_rel_path).resolve(),
            tests_dir=tests_dir,
            runs_dir=runs_dir,
        )
        for field_path in (
            paths.src_dir,
            paths.solver_path,
            paths.baseline_path,
            paths.evaluator_path,
            paths.guardrails_path,
            paths.unit_test_path,
            paths.tests_dir,
            paths.runs_dir,
        ):
            paths.ensure_within_sandbox(field_path)
        return paths

    def ensure_within_sandbox(self, target: Path | str) -> Path:
        """Verify that `target` resolves strictly inside `project_root`."""
        resolved = Path(target).resolve()
        if not resolved.is_relative_to(self.project_root):
            raise GuardrailViolation(
                f"Path escapes project sandbox: {resolved} is outside {self.project_root}"
            )
        return resolved

    def ensure_mutable_target(self, target: Path | str) -> Path:
        """Allow writes only to `solver.py` or artifacts under `runs/`."""
        resolved = self.ensure_within_sandbox(target)
        if resolved == self.solver_path or resolved.is_relative_to(self.runs_dir):
            return resolved
        raise GuardrailViolation(
            f"Refused write to locked path: {resolved}. "
            "Only solver.py and runs/ may be modified during RSI cycles."
        )

    def locked_files(self) -> tuple[Path, ...]:
        """Return all files whose integrity must remain invariant during a run."""
        candidates = [
            self.baseline_path,
            self.evaluator_path,
            self.guardrails_path,
            self.unit_test_path,
            self.tests_dir / "test_solver.py",
            self.tests_dir / "test_route_solver.py",
            self.tests_dir / "test_guardrails.py",
            self.tests_dir / "test_loop.py",
        ]
        seen: set[Path] = set()
        locked: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists() and resolved not in seen:
                seen.add(resolved)
                locked.append(resolved)
        return tuple(locked)


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LockedFileManifest:
    """Snapshots SHA-256 hashes of locked files to prevent test/rule tampering."""

    def __init__(self, files: Iterable[Path]) -> None:
        self._hashes: dict[Path, str] = {
            Path(f).resolve(): sha256_file(Path(f).resolve()) for f in files
        }

    @property
    def hashes(self) -> dict[Path, str]:
        return dict(self._hashes)

    def verify(self) -> None:
        """Raise TamperDetectedError if any locked file changed or disappeared."""
        for path, expected_hash in self._hashes.items():
            if not path.exists():
                raise TamperDetectedError(f"Locked file deleted during run: {path}")
            current_hash = sha256_file(path)
            if current_hash != expected_hash:
                raise TamperDetectedError(
                    f"Locked file modified during run (anti-tamper triggered): {path}"
                )


def validate_max_cycles(max_cycles: int) -> int:
    """Enforce the hard iteration cap."""
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool):
        raise GuardrailViolation("max_cycles must be an integer")
    if max_cycles < 1 or max_cycles > HARD_MAX_CYCLES:
        raise GuardrailViolation(
            f"max_cycles={max_cycles} violates hard bounds [1, {HARD_MAX_CYCLES}]"
        )
    return max_cycles


def validate_candidate_ast(source: str, entrypoint: str = "extract_record") -> None:
    """Statically inspect candidate solver Python code before writing or running it."""
    if not isinstance(source, str) or not source.strip():
        raise GuardrailViolation("Candidate solver source must be a non-empty string")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise GuardrailViolation(f"Candidate solver has syntax error: {exc}") from exc

    has_entrypoint = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_pkg = alias.name.split(".")[0]
                if top_pkg not in ALLOWED_SOLVER_IMPORTS:
                    raise GuardrailViolation(
                        f"Disallowed import in candidate solver: '{alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top_pkg = module.split(".")[0]
            if node.level != 0 or top_pkg not in ALLOWED_SOLVER_IMPORTS:
                raise GuardrailViolation(
                    f"Disallowed from-import in candidate solver: '{module}'"
                )
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_CALL_OR_NAME_NODES:
                raise GuardrailViolation(
                    f"Forbidden builtin/symbol in candidate solver: '{node.id}'"
                )
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                raise GuardrailViolation(
                    f"Forbidden attribute access in candidate solver: '{node.attr}'"
                )
        elif isinstance(node, ast.FunctionDef) and node.name == entrypoint:
            has_entrypoint = True
            if len(node.args.posonlyargs) + len(node.args.args) < 1:
                raise GuardrailViolation(
                    f"{entrypoint} must accept at least one positional argument"
                )

    if not has_entrypoint:
        raise GuardrailViolation(
            f"Candidate solver must define top-level `def {entrypoint}(...)`"
        )


def check_candidate_acceptance(
    best_composite: float,
    best_accuracy: float,
    candidate_composite: float,
    candidate_accuracy: float,
    unit_test_pass_rate: float,
    avg_latency_ms: float,
    min_improvement: float = MIN_SCORE_IMPROVEMENT,
    max_avg_latency_ms: float = MAX_AVG_LATENCY_MS,
) -> tuple[bool, str]:
    """Decide whether to keep a candidate or roll back to the previous best."""
    if unit_test_pass_rate < 1.0:
        return (
            False,
            f"Unit tests failed (pass_rate={unit_test_pass_rate:.2f} < 1.00); rolled back.",
        )
    if avg_latency_ms > max_avg_latency_ms:
        return (
            False,
            f"Latency budget exceeded ({avg_latency_ms:.3f}ms > {max_avg_latency_ms:.1f}ms); rolled back.",
        )
    if candidate_accuracy < best_accuracy:
        return (
            False,
            f"Benchmark accuracy regressed ({candidate_accuracy:.4f} < {best_accuracy:.4f}); rolled back.",
        )
    if candidate_composite <= best_composite + min_improvement:
        return (
            False,
            f"No strict score improvement ({candidate_composite:.4f} <= {best_composite:.4f}); rolled back.",
        )
    return (
        True,
        f"Accepted: composite score improved from {best_composite:.4f} to {candidate_composite:.4f}.",
    )
