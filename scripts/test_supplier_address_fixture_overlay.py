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
        baseline = root / ".address-baseline"
        original_checkout = baseline if baseline.exists() else root
        self.original = guard.git(original_checkout, "show", guard.BASE + ":" + guard.FIXTURE)
        # A shallow candidate checkout contains HEAD; exact fixture SHA remains checked by the guard.
        self.reviewed = guard.git(root, "show", "HEAD:" + guard.FIXTURE)

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


    def test_committed_lf_overlay_passes_and_packet_crlf_is_rejected(self):
        import json
        root = pathlib.Path(__file__).resolve().parents[1]
        overlay = json.loads((root / "docs/procurement-supplier-address-fixture-startup-overlay.json").read_text(encoding="utf-8"))
        committed = guard.git(root, "show", "HEAD:docs/procurement-supplier-address-fixture-overlay.json")
        self.assertNotIn(b"\r\n", committed)
        guard.require_previous_overlay(overlay, committed)
        with self.assertRaises(ValueError):
            guard.require_previous_overlay(overlay, committed.replace(b"\n", b"\r\n"))

    def test_helper_exact_phase_and_drift_custody(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        helper = guard.git(root, "show", "HEAD:" + guard.HELPER)
        guard.require_helper_binding(helper, None, False)
        guard.require_helper_binding(helper, helper, True)
        for candidate, baseline, verify in [(helper + b"drift", None, False), (helper, helper, False),
                                             (helper, None, True), (helper, helper + b"drift", True)]:
            with self.subTest(verify=verify), self.assertRaises(ValueError):
                guard.require_helper_binding(candidate, baseline, verify)

    def test_immutable_startup_overlay_predecessor_and_eol(self):
        import copy
        import json
        root = pathlib.Path(__file__).resolve().parents[1]
        overlay = json.loads((root / "docs/procurement-supplier-address-fixture-journal-overlay.json").read_text(encoding="utf-8"))
        raw = guard.git(root, "show", "HEAD:docs/procurement-supplier-address-fixture-startup-overlay.json")
        guard.require_previous_startup_overlay(overlay, raw)
        with self.assertRaises(ValueError):
            guard.require_previous_startup_overlay(overlay, raw.replace(b"\n", b"\r\n"))
        for field in overlay["previousReviewedStartupOverlay"]:
            mutated = copy.deepcopy(overlay)
            mutated["previousReviewedStartupOverlay"][field] = "drift"
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.require_previous_startup_overlay(mutated, raw)


if __name__ == "__main__":
    unittest.main()
