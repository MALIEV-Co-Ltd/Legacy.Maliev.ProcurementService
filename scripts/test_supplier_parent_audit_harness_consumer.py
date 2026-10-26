"""Exact working/HEAD harness pins and bounded historical reconstruction controls."""
import hashlib
import pathlib
import unittest
from unittest import mock

import procurement_address_null_consumer as consumer


ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED = {
    "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressCountryIdBindingTests.cs":
        ("cbf5e0c303172de15e6e889924b887381cbeb912", "b21c6970729ad6c7982d4a361ab81131d35a8120"),
    "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredBodyIdTests.cs":
        ("d7c932bd34106d9217f4bda29fea1a43ca9df443", "2447ea79cf8e1b5692feea9479cb6beccafd18fc"),
    "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredAuditDateTests.cs":
        ("16109c5013df74ad4c27f14b128287ceb649efb1", "d1f80a5bf248ae8dd51de591221a3fa3a3ace1c5"),
    "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs":
        ("7577a3e8b22e65d68bffd720f2924af7523ba712", "7bdd29d8f13395e8acd851684fb3a1137f571047"),
}


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def current_bytes(path):
    with (ROOT / path).open("rb") as stream:
        return stream.read(1024 * 1024 + 1)


class SupplierParentAuditHarnessConsumerTests(unittest.TestCase):
    def test_four_actual_candidate_files_reconstruct_exact_frozen_git_blobs(self):
        self.assertEqual(EXPECTED, {
            path: binding[:2] for path, binding in consumer.SUPPLIER_PARENT_AUDIT_HARNESSES.items()
        })
        for path, (before, after) in EXPECTED.items():
            with self.subTest(path=path):
                raw = current_bytes(path)
                self.assertEqual(after, git_blob(raw))
                original = consumer.supplier_parent_audit_original_harness(path, raw)
                self.assertIs(type(original), bytes)
                self.assertEqual(before, git_blob(original))
                self.assertNotEqual(original, raw)

    def test_exact_runtime_successors_reject_missing_unknown_and_advanced_preimages(self):
        for path, (before, after) in EXPECTED.items():
            with self.subTest(path=path):
                self.assertEqual(after, consumer.supplier_parent_audit_harness_blob(path, before))
            for wrong in (None, after, "0" * 40):
                with self.subTest(path=path, wrong=wrong), self.assertRaises(ValueError):
                    consumer.supplier_parent_audit_harness_blob(path, wrong)
        for value in (None, "0" * 40, next(iter(EXPECTED.values()))[0]):
            self.assertEqual(value, consumer.supplier_parent_audit_harness_blob("unrelated", value))

    def test_unrelated_bytes_pass_through_without_decoding_or_newline_changes(self):
        for raw in (b"", b"\xff\x00\r\n", b"x" * (1024 * 1024)):
            self.assertIs(raw, consumer.supplier_parent_audit_original_harness("unrelated", raw))

    def test_known_and_unrelated_paths_reject_nonbytes_and_oversized_inputs(self):
        for path in (*EXPECTED, "unrelated"):
            for raw in (None, "source", bytearray(b"source"), memoryview(b"source"),
                        b"x" * (1024 * 1024 + 1)):
                with self.subTest(path=path, kind=type(raw).__name__), self.assertRaises(ValueError):
                    consumer.supplier_parent_audit_original_harness(path, raw)

    def test_extra_occurrence_and_other_byte_substitutions_are_rejected(self):
        for path in EXPECTED:
            raw = current_bytes(path)
            after_hunk = consumer.SUPPLIER_PARENT_AUDIT_HARNESSES[path][3]
            for changed in (raw + after_hunk, raw + b"\n", b" " + raw, raw[:-1]):
                with self.subTest(path=path, size=len(changed)), self.assertRaises(ValueError):
                    consumer.supplier_parent_audit_original_harness(path, changed)

    def test_old_frozen_bytes_cannot_be_presented_as_current_successors(self):
        for path in EXPECTED:
            original = consumer.supplier_parent_audit_original_harness(path, current_bytes(path))
            with self.subTest(path=path), self.assertRaises(ValueError):
                consumer.supplier_parent_audit_original_harness(path, original)

    def test_inverse_requires_exactly_one_after_hunk_even_with_matching_current_pin(self):
        for path in EXPECTED:
            before, _, old_hunk, new_hunk = consumer.SUPPLIER_PARENT_AUDIT_HARNESSES[path]
            raw = current_bytes(path)
            for changed in (raw.replace(new_hunk, b"", 1), raw + new_hunk):
                binding = (before, git_blob(changed), old_hunk, new_hunk)
                with self.subTest(path=path), mock.patch.dict(
                        consumer.SUPPLIER_PARENT_AUDIT_HARNESSES, {path: binding}):
                    with self.assertRaisesRegex(ValueError, "Unique Supplier parent-audit harness inverse"):
                        consumer.supplier_parent_audit_original_harness(path, changed)

    def test_inverse_must_match_exact_original_git_blob(self):
        for path in EXPECTED:
            _, after, old_hunk, new_hunk = consumer.SUPPLIER_PARENT_AUDIT_HARNESSES[path]
            binding = ("0" * 40, after, old_hunk, new_hunk)
            with self.subTest(path=path), mock.patch.dict(
                    consumer.SUPPLIER_PARENT_AUDIT_HARNESSES, {path: binding}):
                with self.assertRaisesRegex(ValueError, "Exact Supplier parent-audit original harness"):
                    consumer.supplier_parent_audit_original_harness(path, current_bytes(path))

    def check_harnesses(self, working, heads):
        candidate = object()
        calls = []
        def blob(root, path):
            self.assertIs(candidate, root)
            self.assertIn(path, EXPECTED)
            calls.append(("working", path))
            return working.get(path)
        def git(root, *args):
            self.assertIs(candidate, root)
            self.assertEqual("rev-parse", args[0])
            self.assertEqual(2, len(args))
            self.assertTrue(args[1].startswith("HEAD:"))
            path = args[1][5:]
            self.assertIn(path, EXPECTED)
            calls.append(("HEAD", path))
            return ((heads.get(path) or "") + "\n").encode("ascii")
        result = consumer.require_supplier_parent_audit_harnesses(candidate, blob, git)
        return result, calls

    def test_closed_set_requirement_checks_each_exact_working_and_head_successor(self):
        values = {path: after for path, (_, after) in EXPECTED.items()}
        result, calls = self.check_harnesses(values, values)
        self.assertEqual(set(EXPECTED), result)
        self.assertEqual([item for path in EXPECTED
                          for item in (("working", path), ("HEAD", path))], calls)

    def test_every_wrong_working_or_head_pin_is_rejected(self):
        values = {path: after for path, (_, after) in EXPECTED.items()}
        for path, (before, _) in EXPECTED.items():
            for wrong in (None, before, "0" * 40):
                for side in ("working", "HEAD"):
                    changed = dict(values)
                    if wrong is None:
                        del changed[path]
                    else:
                        changed[path] = wrong
                    with self.subTest(path=path, wrong=wrong, side=side), self.assertRaises(ValueError):
                        self.check_harnesses(changed if side == "working" else values,
                                             changed if side == "HEAD" else values)


if __name__ == "__main__":
    unittest.main()
