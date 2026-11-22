"""Locked contract unit tests for `rsi_demo.solver`.

These tests must pass for the baseline solver and for every accepted
candidate during RSI runs. They are integrity-checked against tampering.
"""

from __future__ import annotations

import unittest

from rsi_demo.solver import extract_record


class TestSolverContract(unittest.TestCase):
    """Core behavioral invariants every solver version must uphold."""

    def test_empty_and_whitespace_return_empty_dict(self) -> None:
        self.assertEqual(extract_record(""), {})
        self.assertEqual(extract_record("   \n\t  "), {})

    def test_non_string_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            extract_record(123)  # type: ignore[arg-type]

    def test_clean_json_object_roundtrip(self) -> None:
        record = extract_record('{"service": "billing", "port": 8080, "ok": true}')
        self.assertEqual(record, {"service": "billing", "port": 8080, "ok": True})

    def test_simple_key_value_lines_preserve_keys(self) -> None:
        record = extract_record("owner: alice\nenv: staging")
        self.assertEqual(record.get("owner"), "alice")
        self.assertEqual(record.get("env"), "staging")

    def test_values_with_colons_are_not_truncated(self) -> None:
        record = extract_record(
            "endpoint: https://api.example.com:8443/v1\n"
            "timestamp: 2026-03-10T14:22:00Z"
        )
        self.assertEqual(record.get("endpoint"), "https://api.example.com:8443/v1")
        self.assertEqual(record.get("timestamp"), "2026-03-10T14:22:00Z")

    def test_return_type_is_always_dict(self) -> None:
        for sample in ("unstructured text", "{}", "key: value", "---"):
            self.assertIsInstance(extract_record(sample), dict)


if __name__ == "__main__":
    unittest.main()
