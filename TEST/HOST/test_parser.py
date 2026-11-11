"""Guard semantics that instrumentation must preserve before TP compilation."""

import unittest
from pascal import Pascal


class InstrumentationTests(unittest.TestCase):
    def test_io_directives_survive_in_order(self):
        source = (
            "program P; begin {$I-} Write(F,'x'); {$I+} if IOResult=0 then X:=1 end."
        )
        output = Pascal(source, "P.PAS").parse().instrument()
        self.assertEqual(output.count("{$I-}"), 1)
        self.assertEqual(output.count("{$I+}"), 1)
        self.assertLess(output.index("{$I-}"), output.index("Write(F,'x')"))
        self.assertLess(output.index("Write(F,'x')"), output.index("{$I+}"))
        self.assertLess(output.index("{$I+}"), output.index("IOResult=0"))

    def test_directive_does_not_detach_dangling_else(self):
        source = (
            "program P; begin if A then {$I-} if B then X:=1 else X:=2; {$I+} Y:=3 end."
        )
        parser = Pascal(source, "P.PAS").parse()
        outer = parser.routines[0].body.children[0]
        self.assertEqual(outer.kind, "if")
        self.assertEqual(len(outer.children), 1)
        inner = outer.children[0].children[0]
        self.assertEqual(inner.kind, "if")
        self.assertEqual(len(inner.children), 2)
        self.assertIn("{$I-}", parser.instrument())

    def test_asm_keeps_original_instructions_and_ends(self):
        source = "program P; begin asm mov ax, $1234; pushf; popf end end."
        output = Pascal(source, "P.PAS").parse().instrument()
        self.assertIn("mov ax, $1234; pushf; popf", output)
        self.assertEqual(output.count("mov ax, $f120"), 1)
        self.assertEqual(output.count("mov ax, $f122"), 1)


if __name__ == "__main__":
    unittest.main()
