"""Immutable v0 baseline solver for semi-structured text-to-JSON extraction.

This file is locked during RSI runs and serves as the clean starting point
when initializing or resetting `solver.py`.
"""

from __future__ import annotations

import json
from typing import Any

SOLVER_VERSION = "v0-baseline"


def extract_record(text: str) -> dict[str, Any]:
    """Extract a normalized key-value dictionary from semi-structured text.

    Baseline strategy (v0):
    1. Attempt direct JSON object parsing on the trimmed input.
    2. Otherwise split line-by-line on the first ':' and store raw strings.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    cleaned = text.strip()
    if not cleaned:
        return {}

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

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
