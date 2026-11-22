"""Candidate improvement proposers for the RSI loop.

Provides:
- `MockProposer`: deterministic, zero-dependency offline proposer that inspects
  evaluation failures and proposes targeted Python solver improvements
  (including an intentional regression cycle to demonstrate rollback guardrails).
- `OpenAICompatibleProposer`: optional live LLM backend using Python stdlib
  `urllib.request` when configured via CLI flags or environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Protocol
import urllib.error
import urllib.request

from rsi_demo.evaluator import EvaluationReport


@dataclass(frozen=True)
class Proposal:
    """A candidate change proposed for a single RSI cycle."""

    version_label: str
    hypothesis: str
    rationale: str
    target_failure_tags: tuple[str, ...]
    candidate_source: str


class Proposer(Protocol):
    """Interface implemented by offline and LLM-backed proposers."""

    name: str

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict[str, Any]],
    ) -> Proposal:
        """Generate a candidate solver improvement from current failures."""


_V1_SOURCE = '''"""Active solver module iteratively improved during RSI cycles."""

from __future__ import annotations

import json
import re
from typing import Any

SOLVER_VERSION = "v1-json-recovery"


def _try_parse_json_blob(blob: str) -> dict[str, Any] | None:
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", blob.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _extract_embedded_json(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\\s*(\\{.*?\\})\\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        parsed = _try_parse_json_blob(block)
        if parsed is not None:
            return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _try_parse_json_blob(text[start : end + 1])
        if parsed is not None:
            return parsed
    return None


def extract_record(text: str) -> dict[str, Any]:
    """Extract a normalized key-value dictionary from semi-structured text."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    cleaned = text.strip()
    if not cleaned:
        return {}

    direct = _try_parse_json_blob(cleaned)
    if direct is not None:
        return direct

    embedded = _extract_embedded_json(cleaned)
    if embedded is not None:
        return embedded

    result: dict[str, Any] = {}
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value

    return result
'''


_V2_SOURCE = '''"""Active solver module iteratively improved during RSI cycles."""

from __future__ import annotations

import json
import re
from typing import Any

SOLVER_VERSION = "v2-kv-coercion"

_BOOL_TRUE = frozenset({"true", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "no", "off"})
_NULL_VALUES = frozenset({"null", "none"})


def _try_parse_json_blob(blob: str) -> dict[str, Any] | None:
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", blob.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _extract_embedded_json(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\\s*(\\{.*?\\})\\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        parsed = _try_parse_json_blob(block)
        if parsed is not None:
            return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _try_parse_json_blob(text[start : end + 1])
        if parsed is not None:
            return parsed
    return None


def _coerce_value(raw: str) -> Any:
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        return val[1:-1]

    low = val.lower()
    if low in _NULL_VALUES:
        return None
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False

    numeric_str = val[1:].strip() if val.startswith("$") else val
    if re.fullmatch(r"[+-]?\\d+", numeric_str):
        return int(numeric_str)
    if re.fullmatch(r"[+-]?(?:\\d+\\.\\d*|\\.\\d+)", numeric_str):
        return float(numeric_str)
    return val


def _split_delimiter_index(segment: str) -> int:
    colon_idx = segment.find(":")
    eq_idx = segment.find("=")
    if colon_idx == -1:
        return eq_idx
    if eq_idx == -1:
        return colon_idx
    return min(colon_idx, eq_idx)


def extract_record(text: str) -> dict[str, Any]:
    """Extract a normalized key-value dictionary from semi-structured text."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    cleaned = text.strip()
    if not cleaned:
        return {}

    direct = _try_parse_json_blob(cleaned)
    if direct is not None:
        return direct

    embedded = _extract_embedded_json(cleaned)
    if embedded is not None:
        return embedded

    result: dict[str, Any] = {}
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        for segment in re.split(r"[;,]", stripped):
            part = segment.strip()
            if not part:
                continue
            sep_idx = _split_delimiter_index(part)
            if sep_idx <= 0:
                continue
            key = part[:sep_idx].strip()
            raw_val = part[sep_idx + 1 :].strip()
            if key:
                result[key] = _coerce_value(raw_val)

    return result
'''


_V3_REGRESSION_SOURCE = '''"""Active solver module iteratively improved during RSI cycles."""

from __future__ import annotations

import json
import re
from typing import Any

SOLVER_VERSION = "v3-naive-regex-regression"

_BOOL_TRUE = frozenset({"true", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "no", "off"})
_NULL_VALUES = frozenset({"null", "none"})


def _try_parse_json_blob(blob: str) -> dict[str, Any] | None:
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", blob.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _extract_embedded_json(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\\s*(\\{.*?\\})\\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        parsed = _try_parse_json_blob(block)
        if parsed is not None:
            return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _try_parse_json_blob(text[start : end + 1])
        if parsed is not None:
            return parsed
    return None


def _coerce_value(raw: str) -> Any:
    val = raw.strip().strip('"').strip("'")
    low = val.lower()
    if low in _NULL_VALUES:
        return None
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    numeric_str = val[1:].strip() if val.startswith("$") else val
    if re.fullmatch(r"[+-]?\\d+", numeric_str):
        return int(numeric_str)
    if re.fullmatch(r"[+-]?(?:\\d+\\.\\d*|\\.\\d+)", numeric_str):
        return float(numeric_str)
    return val


def extract_record(text: str) -> dict[str, Any]:
    """Attempted regex simplification (intentionally flawed on colons in values)."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    cleaned = text.strip()
    if not cleaned:
        return {}

    direct = _try_parse_json_blob(cleaned)
    if direct is not None:
        return direct

    embedded = _extract_embedded_json(cleaned)
    if embedded is not None:
        return embedded

    # Flaw: stops matching value at ':' which truncates URLs and timestamps.
    result: dict[str, Any] = {}
    for key, val in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\\s*[:=]\\s*([^,;:\\n]+)", cleaned):
        result[key.lower()] = _coerce_value(val)
    return result
'''


_V3_FIXED_SOURCE = '''"""Active solver module iteratively improved during RSI cycles."""

from __future__ import annotations

import json
import re
from typing import Any

SOLVER_VERSION = "v3-quote-aware-aliasing"

_BOOL_TRUE = frozenset({"true", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "no", "off"})
_NULL_VALUES = frozenset({"null", "none"})
_KEY_ALIASES = {
    "user_email": "email",
    "mail": "email",
    "qty": "quantity",
    "amt": "amount",
    "price": "amount",
}


def _try_parse_json_blob(blob: str) -> dict[str, Any] | None:
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", blob.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _extract_embedded_json(text: str) -> dict[str, Any] | None:
    fenced = re.findall(r"```(?:json)?\\s*(\\{.*?\\})\\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        parsed = _try_parse_json_blob(block)
        if parsed is not None:
            return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _try_parse_json_blob(text[start : end + 1])
        if parsed is not None:
            return parsed
    return None


def _split_top_level(text: str) -> list[str]:
    """Split on newlines, commas, and semicolons only outside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote_char: str | None = None
    escaped = False

    for ch in text:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\\\":
            buf.append(ch)
            escaped = True
            continue
        if ch in ('"', "'"):
            if quote_char is None:
                quote_char = ch
            elif quote_char == ch:
                quote_char = None
            buf.append(ch)
            continue
        if quote_char is None and ch in ("\\n", ",", ";"):
            segment = "".join(buf).strip()
            if segment:
                parts.append(segment)
            buf.clear()
            continue
        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _normalize_key(raw_key: str) -> str:
    norm = raw_key.strip().lower().replace(" ", "_")
    return _KEY_ALIASES.get(norm, norm)


def _coerce_value(raw: str) -> Any:
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        return val[1:-1]

    low = val.lower()
    if low in _NULL_VALUES:
        return None
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False

    numeric_str = val[1:].strip() if val.startswith("$") else val
    if re.fullmatch(r"[+-]?\\d+", numeric_str):
        return int(numeric_str)
    if re.fullmatch(r"[+-]?(?:\\d+\\.\\d*|\\.\\d+)", numeric_str):
        return float(numeric_str)
    return val


def _split_delimiter_index(segment: str) -> int:
    colon_idx = segment.find(":")
    eq_idx = segment.find("=")
    if colon_idx == -1:
        return eq_idx
    if eq_idx == -1:
        return colon_idx
    return min(colon_idx, eq_idx)


def extract_record(text: str) -> dict[str, Any]:
    """Extract a normalized key-value dictionary from semi-structured text."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    cleaned = text.strip()
    if not cleaned:
        return {}

    direct = _try_parse_json_blob(cleaned)
    if direct is not None:
        return direct

    embedded = _extract_embedded_json(cleaned)
    if embedded is not None:
        return embedded

    result: dict[str, Any] = {}
    for segment in _split_top_level(cleaned):
        if segment.startswith("#") or segment.startswith("---"):
            continue
        sep_idx = _split_delimiter_index(segment)
        if sep_idx <= 0:
            continue
        key = _normalize_key(segment[:sep_idx])
        raw_val = segment[sep_idx + 1 :].strip()
        if key:
            result[key] = _coerce_value(raw_val)

    return result
'''


_V4_PLATEAU_SOURCE = _V3_FIXED_SOURCE.replace(
    'SOLVER_VERSION = "v3-quote-aware-aliasing"',
    'SOLVER_VERSION = "v4-plateau-noop"',
)


class MockProposer:
    """Offline deterministic proposer driven by observed failure tags."""

    name = "mock-offline"

    def __init__(self, include_regression_demo: bool = True) -> None:
        self.include_regression_demo = include_regression_demo

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict[str, Any]],
    ) -> Proposal:
        failure_tags = {tag for f in report.failures for tag in f.tags}
        tried_versions = {entry.get("proposed_version") for entry in history}

        if (
            {"fenced_json", "embedded_json", "trailing_comma"} & failure_tags
            and "v1-json-recovery" not in tried_versions
        ):
            return Proposal(
                version_label="v1-json-recovery",
                hypothesis="Extract fenced and embedded JSON blocks with trailing-comma cleanup.",
                rationale=(
                    f"Observed {len(report.failures)} failing cases including fenced/embedded JSON "
                    "wrapped in commentary."
                ),
                target_failure_tags=("fenced_json", "embedded_json", "trailing_comma"),
                candidate_source=_V1_SOURCE,
            )

        if (
            {"kv_inline", "type_coercion", "comments_banners", "equals_delimiter", "currency"}
            & failure_tags
            and "v2-kv-coercion" not in tried_versions
        ):
            return Proposal(
                version_label="v2-kv-coercion",
                hypothesis="Support inline ',', ';' and '=' delimiters, skip banners/comments, and coerce types.",
                rationale=(
                    "Inline key=value records, comment lines, currency values, and typed primitives "
                    "currently remain raw strings or are skipped."
                ),
                target_failure_tags=("kv_inline", "type_coercion", "comments_banners"),
                candidate_source=_V2_SOURCE,
            )

        if (
            self.include_regression_demo
            and ({"quoted_delimiters", "key_aliases"} & failure_tags)
            and "v3-naive-regex-regression" not in tried_versions
        ):
            return Proposal(
                version_label="v3-naive-regex-regression",
                hypothesis="Replace line splitter with a single regex key=value matcher and lowercase keys.",
                rationale=(
                    "Attempting a compact regex refactor to handle inline pairs and key casing."
                ),
                target_failure_tags=("quoted_delimiters", "key_aliases"),
                candidate_source=_V3_REGRESSION_SOURCE,
            )

        if (
            {"quoted_delimiters", "key_aliases", "colons_in_values"} & failure_tags
            and "v3-quote-aware-aliasing" not in tried_versions
        ):
            return Proposal(
                version_label="v3-quote-aware-aliasing",
                hypothesis="Use quote-aware field splitting, first-delimiter preservation, and key aliasing.",
                rationale=(
                    "Previous naive regex broke colons inside URLs/timestamps; quote-aware scanning "
                    "preserves quoted commas/colons and maps canonical aliases."
                ),
                target_failure_tags=("quoted_delimiters", "key_aliases", "colons_in_values"),
                candidate_source=_V3_FIXED_SOURCE,
            )

        return Proposal(
            version_label="v4-plateau-noop",
            hypothesis="Attempt minor version/whitespace normalization at convergence plateau.",
            rationale="All benchmark cases already pass or no safe heuristic delta remains.",
            target_failure_tags=tuple(sorted(failure_tags)),
            candidate_source=_V4_PLATEAU_SOURCE,
        )


class OpenAICompatibleProposer:
    """Optional live LLM proposer using an OpenAI-compatible chat completions API."""

    name = "llm-openai-compatible"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("RSI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or os.environ.get("RSI_LLM_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("RSI_LLM_MODEL") or "gpt-4o-mini"
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ValueError(
                "LLM backend requires RSI_LLM_API_KEY or OPENAI_API_KEY environment variable."
            )

    def propose(
        self,
        cycle: int,
        current_source: str,
        report: EvaluationReport,
        history: list[dict[str, Any]],
    ) -> Proposal:
        failure_preview = [
            {
                "case_id": f.case_id,
                "tags": f.tags,
                "input_text": f.input_text,
                "expected": f.expected,
                "actual": f.actual,
                "error": f.error,
            }
            for f in report.failures[:5]
        ]
        prompt = (
            "You are improving a Python module `solver.py` that implements "
            "`extract_record(text: str) -> dict`.\n"
            "Constraints:\n"
            "- Only import from: json, re, typing, math, dataclasses, collections, string, __future__.\n"
            "- Never use eval, exec, open, os, sys, subprocess, getattr, or globals.\n"
            "- Preserve existing passing behavior and URLs/timestamps containing colons.\n"
            "- Return ONLY valid JSON with keys: version_label, hypothesis, rationale, candidate_source.\n\n"
            f"Cycle: {cycle}\n"
            f"Current composite_score: {report.composite_score}, accuracy: {report.accuracy}\n"
            f"Top failures:\n{json.dumps(failure_preview, indent=2)}\n\n"
            f"Current solver.py:\n```python\n{current_source}\n```"
        )

        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a careful Python software engineer generating safe, pure-stdlib code.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM proposal request failed: {exc}") from exc

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return Proposal(
            version_label=str(parsed.get("version_label", f"llm-cycle-{cycle}")),
            hypothesis=str(parsed.get("hypothesis", "LLM-proposed solver improvement")),
            rationale=str(parsed.get("rationale", "")),
            target_failure_tags=tuple(sorted({t for f in report.failures for t in f.tags})),
            candidate_source=str(parsed["candidate_source"]),
        )
