"""A proof must fail closed when its source or execution contradicts it."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
from config import WORK
from reachability import audit


class ReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((WORK / "UNIT/INDEX.json").read_text())
        cls.catalogue = json.loads(
            (ROOT / "TEST/UNREACHABLE.json").read_text(encoding="utf-8")
        )

    def test_changed_source_cannot_be_excluded(self):
        with patch("reachability.source_digest", return_value="changed"):
            excluded, errors = audit(
                ROOT, self.index, set(), list(self.index["modules"])
            )
        self.assertTrue(errors)
        self.assertEqual(excluded, [])

    def test_executed_point_refutes_proof(self):
        entry = self.catalogue["proofs"][0]["points"][0]
        points = [
            p for p in self.index["points"] if p["file"] == entry["module"] + ".PAS"
        ]
        number = points[entry["local_id"] - 1]["id"]
        excluded, errors = audit(ROOT, self.index, {number}, [entry["module"]])
        self.assertTrue(any("Опровергнута" in error for error in errors))
        self.assertNotIn(number, {p["id"] for p in excluded})


if __name__ == "__main__":
    unittest.main()
