"""Trust-boundary controls for the exact Supplier-address parent audit successor."""
import pathlib
import unittest
from unittest import mock

import procurement_address_null_consumer as consumer


REPOSITORY = "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"
BEFORE = "f116b6f1f0258f2f3bfd0eb35190bd14a64c06f4"
AFTER = "54cb841a000af128f8cac90028966577983f3228"
TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/SupplierAddressParentAuditSourceHttpTests.cs"
TEST_BLOB = "52aa910abfbbb7c19aa4e4cf84ac3c87e7975f00"


class SupplierParentAuditConsumerTests(unittest.TestCase):
    def test_exact_inventory_transition_preserves_previous_and_every_unrelated_entry(self):
        previous = {REPOSITORY: "100644 blob " + BEFORE,
                    "unrelated": "100644 blob " + "a" * 40}
        snapshot = dict(previous)
        current = consumer.supplier_parent_audit_consumer_inputs(previous)
        self.assertEqual(snapshot, previous)
        self.assertIsNot(previous, current)
        self.assertEqual({**snapshot, REPOSITORY: "100644 blob " + AFTER}, current)

    def test_inventory_rejects_missing_unknown_advanced_and_wrong_mode_preimages(self):
        for value in (None, "100644 blob " + "0" * 40,
                      "100644 blob " + AFTER, "100755 blob " + BEFORE):
            previous = {"unrelated": "100644 blob " + "a" * 40}
            if value is not None:
                previous[REPOSITORY] = value
            snapshot = dict(previous)
            with self.subTest(value=value), self.assertRaises(ValueError):
                consumer.supplier_parent_audit_consumer_inputs(previous)
            self.assertEqual(snapshot, previous)

    def test_runtime_transform_requires_exact_preimage_and_preserves_other_paths(self):
        self.assertEqual(AFTER, consumer.supplier_parent_audit_runtime_blob(REPOSITORY, BEFORE))
        for value in (None, "0" * 40, AFTER):
            with self.subTest(value=value), self.assertRaises(ValueError):
                consumer.supplier_parent_audit_runtime_blob(REPOSITORY, value)
        for value in (None, BEFORE, AFTER, "0" * 40):
            with self.subTest(unrelated=value):
                self.assertEqual(value, consumer.supplier_parent_audit_runtime_blob("unrelated", value))

    def test_runtime_requirement_accepts_only_exact_working_successor_and_path(self):
        candidate = object()
        for value in (AFTER, BEFORE, None, "0" * 40):
            calls = []
            def blob(root, path):
                calls.append((root, path))
                return value
            with self.subTest(value=value):
                if value == AFTER:
                    self.assertEqual({REPOSITORY},
                                     consumer.require_supplier_parent_audit_runtime(candidate, blob))
                else:
                    with self.assertRaises(ValueError):
                        consumer.require_supplier_parent_audit_runtime(candidate, blob)
                self.assertEqual([(candidate, REPOSITORY)], calls)

    def check_tests(self, working=TEST_BLOB, head=TEST_BLOB, present=False, frozen=b""):
        candidate, baseline = pathlib.Path("candidate"), pathlib.Path("baseline")
        calls = []
        def blob(root, path):
            self.assertEqual(candidate, root)
            self.assertEqual(TEST, path)
            return working
        def git(root, *args):
            calls.append((root, args))
            if root == candidate:
                self.assertEqual(("rev-parse", "HEAD:" + TEST), args)
                return (head or "").encode("ascii")
            self.assertEqual(baseline, root)
            self.assertEqual(("ls-tree", "-r", "--name-only", "frozen-base", "--", TEST), args)
            return frozen
        with mock.patch.object(pathlib.Path, "exists", autospec=True, return_value=present) as exists:
            result = consumer.require_supplier_parent_audit_tests(
                candidate, baseline, blob, git, "frozen-base")
            exists.assert_called_once_with(baseline / TEST)
        return result, calls

    def test_test_requirement_checks_exact_working_head_and_frozen_object(self):
        result, calls = self.check_tests()
        self.assertEqual({TEST}, result)
        self.assertEqual([
            (pathlib.Path("candidate"), ("rev-parse", "HEAD:" + TEST)),
            (pathlib.Path("baseline"),
             ("ls-tree", "-r", "--name-only", "frozen-base", "--", TEST)),
        ], calls)

    def test_missing_or_unknown_working_test_is_rejected(self):
        for wrong in (None, "0" * 40, BEFORE):
            with self.subTest(working=wrong), self.assertRaises(ValueError):
                self.check_tests(working=wrong)

    def test_missing_or_unknown_head_test_is_rejected_even_with_exact_working_test(self):
        for wrong in (None, "0" * 40, BEFORE):
            with self.subTest(head=wrong), self.assertRaises(ValueError):
                self.check_tests(head=wrong)

    def test_frozen_working_test_presence_is_rejected(self):
        with self.assertRaises(ValueError):
            self.check_tests(present=True)

    def test_frozen_object_test_presence_is_rejected_even_without_working_file(self):
        with self.assertRaises(ValueError):
            self.check_tests(frozen=(TEST + "\n").encode("ascii"))


if __name__ == "__main__":
    unittest.main()
