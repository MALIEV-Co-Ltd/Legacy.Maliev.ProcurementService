"""Reject drift without starting either native causal phase."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("overlay", pathlib.Path(__file__).with_name("prepare-supplier-address-causal-baseline.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class FixtureOverlayControls(unittest.TestCase):
    def setUp(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        self.original = guard.git(root, "show", guard.BASE + ":" + guard.FIXTURE)
        self.reviewed = guard.git(root, "show", guard.FIXTURE_PRODUCER + ":" + guard.FIXTURE)

    def test_initial_exact_original_and_reviewed_overlay_pass(self):
        guard.require_fixture_binding(self.reviewed, self.original, self.original, False)

    def test_after_phase_exact_equal_reviewed_fixtures_pass(self):
        guard.require_fixture_binding(self.reviewed, self.reviewed, self.original, True)

    def test_candidate_drift_is_rejected_in_both_phases(self):
        for verify_only in (False, True):
            with self.subTest(verify_only=verify_only), self.assertRaises(ValueError):
                guard.require_fixture_binding(self.reviewed + b"drift", self.reviewed if verify_only else self.original, self.original, verify_only)

    def test_baseline_fixture_drift_is_rejected_in_both_phases(self):
        for verify_only in (False, True):
            with self.subTest(verify_only=verify_only), self.assertRaises(ValueError):
                guard.require_fixture_binding(self.reviewed, b"drift", self.original, verify_only)

    def test_original_provenance_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            guard.require_fixture_binding(self.reviewed, self.original, self.original + b"drift", False)

    def test_causal_case_harness_drift_is_rejected(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        harness = guard.git(root, "show", "HEAD:" + guard.TEST)
        guard.require_harness_binding(harness)
        with self.assertRaises(ValueError):
            guard.require_harness_binding(harness + b"drift")


if __name__ == "__main__":
    unittest.main()
