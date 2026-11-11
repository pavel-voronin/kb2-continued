"""Formatting must preserve cache keys; executable changes must not."""

import unittest
from run import signature


def function(source, filename):
    namespace = {}
    exec(compile(source, filename, "exec"), namespace)
    return namespace["f"].__code__


class CacheTests(unittest.TestCase):
    def test_source_line_and_filename_are_not_behavior(self):
        first = function("def f(x): return x+1", "first.py")
        moved = function("\n\n\ndef f(x):\n    return x + 1\n", "moved.py")
        self.assertEqual(signature(first), signature(moved))

    def test_changed_constant_invalidates_key(self):
        first = function("def f(x): return x+1", "same.py")
        changed = function("def f(x): return x+2", "same.py")
        self.assertNotEqual(signature(first), signature(changed))


if __name__ == "__main__":
    unittest.main()
