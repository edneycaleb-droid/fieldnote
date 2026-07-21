"""Deterministic tests for Fieldnote's extraction normalization boundary."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "agents" / "skill_validator.py"
SPEC = importlib.util.spec_from_file_location("skill_validator", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

LIST_FIELDS = ("steps", "tools", "concepts", "tags", "python_packages", "related_skills")


class SkillValidatorTests(unittest.TestCase):
    def test_null_and_non_dict_inputs_fail_safe(self) -> None:
        for raw in (None, "invalid", 42):
            with self.subTest(raw=raw):
                result = validator.validate_extraction(raw, context="test")
                self.assertTrue(all(result[field] == [] for field in LIST_FIELDS))
                self.assertEqual("", result["action"])
                self.assertIsNone(result["enhance_target"])

    def test_list_fields_are_normalized_without_empty_items(self) -> None:
        result = validator.validate_extraction({
            "steps": " first, ,second ",
            "tools": [" git ", None, ""],
            "concepts": 3,
            "action": " create ",
            "enhance_target": 7,
        })
        self.assertEqual(["first", "second"], result["steps"])
        self.assertEqual(["git"], result["tools"])
        self.assertEqual([], result["concepts"])
        self.assertEqual("create", result["action"])
        self.assertEqual("7", result["enhance_target"])
        self.assertTrue(all(isinstance(result[field], list) for field in LIST_FIELDS))


if __name__ == "__main__":
    unittest.main()
