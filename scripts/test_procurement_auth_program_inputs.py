"""Mutation controls for immutable runtime/public-fixture admission."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("join_guard", pathlib.Path(__file__).with_name("verify-procurement-auth-program.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class RuntimeInputs(unittest.TestCase):
    def setUp(self):
        import tempfile
        import subprocess
        from unittest.mock import patch
        original_root = guard.ROOT
        self.original_root = original_root
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        committed_root = pathlib.Path(temporary.name)
        for source in (original_root / "tools/ProcurementAuthProgram.Tests").glob("public-graph*.json"):
            relative = source.relative_to(original_root)
            if source == guard.MANIFEST:
                continue
            raw = subprocess.check_output(["git", "-C", str(original_root), "show", "HEAD:" + relative.as_posix()], timeout=15)
            target = committed_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        replacement = patch.object(guard, "ROOT", committed_root)
        replacement.start()
        self.addCleanup(replacement.stop)
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
        guard.require_source_change(guard.tracked_inputs(self.original_root), manifest)

    def test_unrelated_drift_is_rejected_even_when_witness_agrees(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = guard.tracked_inputs(self.original_root)
        unchanged = next(path for path in reviewed if path not in manifest["intentionalSourceChanges"]["changedInputs"])
        reviewed[unchanged] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_query_blob_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = guard.tracked_inputs(self.original_root)
        reviewed[next(iter(manifest["intentionalSourceChanges"]["changedInputs"]))] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_each_reviewed_changed_input_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = guard.tracked_inputs(self.original_root)
                reviewed[path] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_each_missing_reviewed_changed_input_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = guard.tracked_inputs(self.original_root)
                del reviewed[path]
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_missing_source_change_record_is_rejected(self):
        with self.assertRaises(KeyError):
            guard.require_source_change(self.reviewed, {})

    def test_current_graph_preserves_exact_historical_custody(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        guard.require_historical_graph(manifest)
        manifest["historicalGraph"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)

    def test_current_graph_rejects_supplier_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["latestAcceptedSupplierGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_supplier_witness_input_count_drift(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        manifest["latestAcceptedSupplierGraph"]["inputCount"] = 64
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)

    def test_current_graph_rejects_bucket_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["latestAcceptedBucketGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_bucket_witness_input_count_drift(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        manifest["latestAcceptedBucketGraph"]["inputCount"] = 65
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)

    def test_current_graph_rejects_purchase_order_address_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement", "inputCount"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["latestAcceptedPurchaseOrderAddressGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_external_pin_or_auth_identity_changes(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("producer", "case-count", "method", "authority"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                if field == "producer":
                    mutated["references"][0]["commit"] = "main"
                elif field == "case-count":
                    mutated["expectedCases"] += 1
                elif field == "method":
                    mutated["expectedMethods"][next(iter(mutated["expectedMethods"]))] += 1
                else:
                    mutated["productionEnrollmentProven"] = True
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_previous_fixture_graph_custody_or_qualification_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement", "inputCount", "qualification"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["previousReviewedFixtureGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)


    def test_committed_lf_fixture_graph_passes_and_packet_crlf_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        guard.require_historical_graph(manifest)
        source = guard.ROOT / manifest["previousReviewedFixtureGraph"]["path"]
        committed = source.read_bytes()
        self.assertNotIn(b"\r\n", committed)
        source.write_bytes(committed.replace(b"\n", b"\r\n"))
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)


if __name__ == "__main__":
    unittest.main()
