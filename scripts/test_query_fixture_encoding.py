"""Reject the concrete fixture encoding corruption before native validation."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("encoding_guard", pathlib.Path(__file__).with_name("verify-query-fixture-encoding.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class FixtureEncoding(unittest.TestCase):
    def test_actual_fixture_has_exact_codepoints(self):
        guard.verify(guard.SOURCE.read_bytes())

    def test_cp1252_mojibake_is_rejected(self):
        corrupted = guard.SOURCE.read_bytes().decode("cp1252").encode("utf-8")
        with self.assertRaises(ValueError):
            guard.verify(corrupted)

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaises(UnicodeDecodeError):
            guard.verify(guard.SOURCE.read_bytes() + b"\xff")

    def test_changed_english_case_is_rejected(self):
        corrupted = guard.SOURCE.read_bytes().replace(b'"PART1234"', b'"part1234"')
        with self.assertRaises(ValueError):
            guard.verify(corrupted)


if __name__ == "__main__":
    unittest.main()
