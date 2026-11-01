"""Static declaration checks: expressions are inspected, never evaluated."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_profile as tool


class LiteralProfileTest(unittest.TestCase):
    def get(self, code, path):
        raw = code.encode()
        return tool.literal(tool.declaration(raw)[path], raw)

    def test_nested_and_dotted_attributes(self):
        self.assertEqual(self.get('{ a = { b.c = "x"; }; }', ("a", "b", "c")), "x")

    def test_quoted_attribute_and_comment(self):
        self.assertEqual(self.get('# code\n{ lib, ... }: { fileSystems."/".device = "/dev/root"; }',
                                  ("fileSystems", "/", "device")), "/dev/root")

    def test_list_of_routes(self):
        self.assertEqual(self.get('{ routes = [ { Gateway = "192.0.2.1"; } ]; }', ("routes",)), [{"Gateway": "192.0.2.1"}])

    def test_default_wrapper_is_recognized_without_calling_it(self):
        self.assertEqual(self.get('{ lib }: { system = lib.mkDefault "x86_64-linux"; }', ("system",)), "x86_64-linux")

    def test_import_readfile_and_arbitrary_function_are_rejected(self):
        for value in ('import /not-authorized', 'builtins.readFile /not-authorized', 'otherFunction "value"'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "NON_LITERAL_VALUE"):
                self.get('{ x = ' + value + '; }', ("x",))

    def test_interpolation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NON_LITERAL_STRING"):
            self.get('{ x = "${builtins.readFile /not-authorized}"; }', ("x",))

    def test_duplicate_binding_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_BINDING"):
            self.get('{ x = "one"; x = "two"; }', ("x",))

    def test_dynamic_outer_expression_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NOT_A_LITERAL_ATTRIBUTE_SET"):
            self.get('let secret = builtins.readFile /not-authorized; in { x = secret; }', ("x",))


if __name__ == "__main__":
    unittest.main()
