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
                self.assertIs(address.require_address_runtime, prep.require_address_runtime)
                self.assertIs(address.require_address_test, prep.require_address_test)
                source = (HERE / filename).read_text(encoding="utf-8")
                self.assertIn("| require_address_runtime(candidate, blob)", source)
                if filename in PREPARERS[2:]:
                    self.assertIn(".add(require_address_test(candidate, blob))", source)
                if filename in PREPARERS[3:]:
                    self.assertIn('tracked_inputs(candidate, 74) == address_consumer_inputs(manifest["reviewedInputs"])', source)
                    self.assertIn('current_inputs = address_consumer_inputs(manifest["reviewedInputs"])', source)


if __name__ == "__main__":
    unittest.main()
