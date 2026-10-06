"""Mutation controls for immutable runtime/public-fixture admission."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("join_guard", pathlib.Path(__file__).with_name("verify-procurement-auth-program.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class RuntimeInputs(unittest.TestCase):
    def setUp(self):
        self.reviewed = {project + "/Input.cs": "100644 blob reviewed" for project in guard.PROJECTS}
        self.reviewed[guard.FIXTURE] = "100644 blob fixture"

    def test_identical_reviewed_runtime_and_fixture_pass(self):
        guard.require_equal(dict(self.reviewed), self.reviewed)

    def test_changed_runtime_blob_is_rejected(self):
        current = dict(self.reviewed)
        current[next(iter(current))] = "100644 blob drift"
        with self.assertRaises(ValueError):
            guard.require_equal(current, self.reviewed)

    def test_added_runtime_input_is_rejected(self):
        current = dict(self.reviewed)
        current[guard.PROJECTS[0] + "/Added.cs"] = "100644 blob added"
        with self.assertRaises(ValueError):
            guard.require_equal(current, self.reviewed)

    def test_missing_runtime_project_is_rejected_even_when_equal(self):
        reviewed = dict(self.reviewed)
        del reviewed[guard.PROJECTS[3] + "/Input.cs"]
        with self.assertRaises(ValueError):
            guard.require_equal(reviewed, reviewed)

    def test_missing_public_fixture_is_rejected_even_when_equal(self):
        reviewed = dict(self.reviewed)
        del reviewed[guard.FIXTURE]
        with self.assertRaises(ValueError):
            guard.require_equal(reviewed, reviewed)


    def test_frozen_literal_changes_keep_other_runtime_inputs(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        guard.require_source_change(guard.tracked_inputs(guard.ROOT), manifest)

    def test_unrelated_drift_is_rejected_even_when_witness_agrees(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = guard.tracked_inputs(guard.ROOT)
        unchanged = next(path for path in reviewed if path not in manifest["intentionalSourceChanges"]["changedInputs"])
        reviewed[unchanged] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_query_blob_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = guard.tracked_inputs(guard.ROOT)
        reviewed[next(iter(manifest["intentionalSourceChanges"]["changedInputs"]))] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_each_reviewed_changed_input_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = guard.tracked_inputs(guard.ROOT)
                reviewed[path] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_each_missing_reviewed_changed_input_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = guard.tracked_inputs(guard.ROOT)
                del reviewed[path]
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_missing_source_change_record_is_rejected(self):
        with self.assertRaises(KeyError):
            guard.require_source_change(self.reviewed, {})


if __name__ == "__main__":
    unittest.main()
