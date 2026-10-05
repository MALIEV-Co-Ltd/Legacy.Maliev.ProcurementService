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


if __name__ == "__main__":
    unittest.main()
