"""Synthetic controls for Issue29's exact current-consumer transition; no SDK or provider."""
import importlib.util
import json
import pathlib
import unittest

import procurement_address_null_consumer as address

HERE = pathlib.Path(__file__).resolve().parent
PREPARERS = (
    "prepare-file-metadata-baseline.py",
    "prepare-supplier-identity-baseline.py",
    "prepare-metadata-identity-baseline.py",
    "prepare-header-ignored-fields-baseline.py",
    "prepare-supplier-ignored-audits-baseline.py",
    "prepare-metadata-ignored-audits-baseline.py",
)


def load_guard(filename):
    spec = importlib.util.spec_from_file_location("address_control_" + filename.replace("-", "_"), HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class AddressNullConsumerControls(unittest.TestCase):
    def test_exact_two_controller_transition_preserves_all_other_inputs_and_preimage(self):
        previous = {path: "100644 blob " + before for path, (before, _) in address.ADDRESS_BINDINGS.items()}
        previous["unrelated"] = "100644 blob " + "a" * 40
        snapshot = dict(previous)
        current = address.address_consumer_inputs(previous)
        self.assertEqual(snapshot, previous)
        self.assertEqual(set(snapshot), set(current))
        self.assertEqual("100644 blob " + "a" * 40, current["unrelated"])
        self.assertEqual(2, len(address.ADDRESS_BINDINGS))
        for path, (_, after) in address.ADDRESS_BINDINGS.items():
            self.assertEqual("100644 blob " + after, current[path])

    def test_each_missing_wrong_or_already_advanced_preimage_is_rejected(self):
        previous = {path: "100644 blob " + before for path, (before, _) in address.ADDRESS_BINDINGS.items()}
        for path, (_, after) in address.ADDRESS_BINDINGS.items():
            for metadata in (None, "100644 blob " + "0" * 40, "100644 blob " + after):
                changed = dict(previous)
                if metadata is None:
                    del changed[path]
                else:
                    changed[path] = metadata
                with self.subTest(path=path, metadata=metadata), self.assertRaises(ValueError):
                    address.address_consumer_inputs(changed)

    def test_current_runtime_and_eight_row_test_are_exact_and_old_missing_unknown_are_rejected(self):
        values = {path: after for path, (_, after) in address.ADDRESS_BINDINGS.items()}
        values[address.ADDRESS_TEST] = address.ADDRESS_TEST_BLOB
        def blob(_, path):
            return values.get(path)
        self.assertEqual(set(address.ADDRESS_BINDINGS), address.require_address_runtime(None, blob))
        self.assertEqual(address.ADDRESS_TEST, address.require_address_test(None, blob))
        for path in tuple(values):
            expected = values[path]
            old = address.ADDRESS_BINDINGS[path][0] if path in address.ADDRESS_BINDINGS else "f" * 40
            for value in (None, "0" * 40, old):
                values[path] = value
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    address.require_address_runtime(None, blob)
            values[path] = expected

    def test_actual_auth_join_rejects_every_controller_and_unrelated_runtime_drift(self):
        guard = load_guard("verify-procurement-auth-program.py")
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        current = guard.tracked_inputs(guard.ROOT)
        guard.require_consumer_inputs(current, producer, manifest)
        for path, (before, _) in address.ADDRESS_BINDINGS.items():
            for value in (None, "100644 blob " + before, "100644 blob " + "0" * 40):
                changed = dict(current)
                if value is None:
                    del changed[path]
                else:
                    changed[path] = value
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    guard.require_consumer_inputs(changed, producer, manifest)
        unrelated = next(path for path in current if path not in address.ADDRESS_BINDINGS)
        for path, value in ((unrelated, None), (unrelated, "100644 blob " + "0" * 40),
                            ("Legacy.Maliev.ProcurementService.Api/foreign.cs", "100644 blob " + "0" * 40)):
            changed = dict(current)
            if value is None:
                del changed[path]
            else:
                changed[path] = value
            with self.subTest(unrelated=path, value=value), self.assertRaises(ValueError):
                guard.require_consumer_inputs(changed, producer, manifest)

    def test_every_causal_preparer_checks_exact_current_controller_and_test_bindings(self):
        for filename in PREPARERS:
            prep = load_guard(filename)
            with self.subTest(filename=filename):
                self.assertIs(address.require_supplier_mutation_runtime, prep.require_supplier_mutation_runtime)
                self.assertIs(address.require_supplier_mutation_tests, prep.require_supplier_mutation_tests)
                self.assertIs(address.require_address_test, prep.require_address_test)
                source = (HERE / filename).read_text(encoding="utf-8")
                self.assertIn("| require_supplier_mutation_runtime(candidate, blob)", source)
                self.assertIn("require_supplier_mutation_tests(candidate, baseline, blob, git, BASE)", source)
                if filename in PREPARERS[2:]:
                    self.assertIn(".add(require_address_test(candidate, blob))", source)
                if filename in PREPARERS[3:]:
                    self.assertIn('tracked_inputs(candidate, 74) == supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))', source)
                    self.assertIn('current_inputs = supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))', source)



class SupplierMutationConsumerControls(unittest.TestCase):
    def test_exact_two_successors_preserve_other_inputs_and_previous_inventory(self):
        previous = {path: "100644 blob " + before
                    for path, (before, _) in address.SUPPLIER_MUTATION_BINDINGS.items()}
        previous["unrelated"] = "100644 blob " + "a" * 40
        snapshot = dict(previous)
        current = address.supplier_mutation_consumer_inputs(previous)
        self.assertEqual(snapshot, previous)
        self.assertEqual(set(previous), set(current))
        self.assertEqual(previous["unrelated"], current["unrelated"])
        self.assertEqual(2, len(address.SUPPLIER_MUTATION_BINDINGS))
        for path, (_, after) in address.SUPPLIER_MUTATION_BINDINGS.items():
            self.assertEqual("100644 blob " + after, current[path])

    def test_missing_unknown_and_already_advanced_preimages_are_rejected(self):
        previous = {path: "100644 blob " + before
                    for path, (before, _) in address.SUPPLIER_MUTATION_BINDINGS.items()}
        for path, (_, after) in address.SUPPLIER_MUTATION_BINDINGS.items():
            for metadata in (None, "100644 blob " + "0" * 40, "100644 blob " + after):
                changed = dict(previous)
                if metadata is None:
                    del changed[path]
                else:
                    changed[path] = metadata
                with self.subTest(path=path, metadata=metadata), self.assertRaises(ValueError):
                    address.supplier_mutation_consumer_inputs(changed)
            self.assertEqual(after, address.supplier_mutation_runtime_blob(path,
                address.SUPPLIER_MUTATION_BINDINGS[path][0]))
            for wrong in (None, "0" * 40, after):
                with self.subTest(path=path, runtime_preimage=wrong), self.assertRaises(ValueError):
                    address.supplier_mutation_runtime_blob(path, wrong)

    def test_current_runtime_requires_both_successors_and_retained_address_bindings(self):
        values = {path: after for path, (_, after) in address.ADDRESS_BINDINGS.items()}
        values.update({path: after for path, (_, after) in address.SUPPLIER_MUTATION_BINDINGS.items()})
        values[address.ADDRESS_TEST] = address.ADDRESS_TEST_BLOB
        def blob(_, path):
            return values.get(path)
        self.assertEqual(set(address.ADDRESS_BINDINGS) | set(address.SUPPLIER_MUTATION_BINDINGS),
                         address.require_supplier_mutation_runtime(None, blob))
        for path, expected in tuple(values.items()):
            old = (address.SUPPLIER_MUTATION_BINDINGS[path][0]
                   if path in address.SUPPLIER_MUTATION_BINDINGS else "f" * 40)
            for wrong in (None, "0" * 40, old):
                values[path] = wrong
                with self.subTest(path=path, value=wrong), self.assertRaises(ValueError):
                    address.require_supplier_mutation_runtime(None, blob)
            values[path] = expected

    def test_actual_auth_join_rejects_both_old_missing_unknown_and_extra_runtime_inputs(self):
        guard = load_guard("verify-procurement-auth-program.py")
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        current = guard.tracked_inputs(guard.ROOT)
        guard.require_consumer_inputs(current, producer, manifest)
        for path, (before, _) in address.SUPPLIER_MUTATION_BINDINGS.items():
            for metadata in (None, "100644 blob " + before, "100644 blob " + "0" * 40):
                changed = dict(current)
                if metadata is None:
                    del changed[path]
                else:
                    changed[path] = metadata
                with self.subTest(path=path, metadata=metadata), self.assertRaises(ValueError):
                    guard.require_consumer_inputs(changed, producer, manifest)
        changed = dict(current)
        changed["Legacy.Maliev.ProcurementService.Api/unreviewed.cs"] = "100644 blob " + "0" * 40
        with self.assertRaises(ValueError):
            guard.require_consumer_inputs(changed, producer, manifest)

    def test_new_test_bindings_require_working_head_and_absent_frozen_baseline(self):
        from unittest import mock
        candidate, baseline = pathlib.Path("candidate"), pathlib.Path("baseline")
        working = dict(address.SUPPLIER_MUTATION_TESTS)
        heads = dict(working)
        baseline_tree = b""
        def blob(root, path):
            self.assertEqual(candidate, root)
            return working.get(path)
        def git(root, *args):
            if root == candidate and args[0] == "rev-parse":
                return (heads.get(args[1][5:]) or "").encode()
            self.assertEqual(baseline, root)
            self.assertEqual(("ls-tree", "-r", "--name-only", "frozen", "--",
                              *address.SUPPLIER_MUTATION_TESTS), args)
            return baseline_tree
        with mock.patch.object(pathlib.Path, "exists", return_value=False):
            self.assertEqual(set(working), address.require_supplier_mutation_tests(
                candidate, baseline, blob, git, "frozen"))
            for mapping in (working, heads):
                for path, expected in tuple(mapping.items()):
                    for wrong in (None, "0" * 40, "f" * 40):
                        mapping[path] = wrong
                        with self.subTest(path=path, value=wrong), self.assertRaises(ValueError):
                            address.require_supplier_mutation_tests(candidate, baseline, blob, git, "frozen")
                    mapping[path] = expected
            baseline_tree = next(iter(working)).encode()
            with self.assertRaises(ValueError):
                address.require_supplier_mutation_tests(candidate, baseline, blob, git, "frozen")
            baseline_tree = b""
        with mock.patch.object(pathlib.Path, "exists", return_value=True), self.assertRaises(ValueError):
            address.require_supplier_mutation_tests(candidate, baseline, blob, git, "frozen")

    def test_every_consumer_preserves_historical_inventory_and_enrolls_exact_successors(self):
        for filename in PREPARERS:
            prep = load_guard(filename)
            source = (HERE / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIs(address.require_supplier_mutation_runtime, prep.require_supplier_mutation_runtime)
                self.assertIs(address.require_supplier_mutation_tests, prep.require_supplier_mutation_tests)
                self.assertEqual("aa83c9ddc65ccac0bfc90974f64a817ad8cbbc68",
                    prep.SUPPLIER_QUERY_RUNTIME[next(iter(address.SUPPLIER_MUTATION_BINDINGS))])
                self.assertIn("| require_supplier_mutation_runtime(candidate, blob)", source)
                if filename in PREPARERS[2:]:
                    target = "allowed_tests" if filename == PREPARERS[2] else "expected_changes"
                    self.assertIn(target + ".update(require_supplier_mutation_tests(candidate, baseline, blob, git, BASE))", source)
                else:
                    self.assertIn("require_supplier_mutation_tests(candidate, baseline, blob, git, BASE)", source)


if __name__ == "__main__":
    unittest.main()
