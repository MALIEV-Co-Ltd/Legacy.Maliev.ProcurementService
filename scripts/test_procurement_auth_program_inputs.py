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
        self.reviewed[guard.JOIN_TEST_PROJECT] = "100644 blob join-test-project"

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


    def test_missing_join_test_project_is_rejected_even_when_equal(self):
        reviewed = dict(self.reviewed)
        del reviewed[guard.JOIN_TEST_PROJECT]
        with self.assertRaises(ValueError):
            guard.require_equal(reviewed, reviewed)

    def test_changed_join_test_project_blob_is_rejected(self):
        current = dict(self.reviewed)
        current[guard.JOIN_TEST_PROJECT] = "100644 blob drift"
        with self.assertRaises(ValueError):
            guard.require_equal(current, self.reviewed)

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


    def test_current_graph_rejects_address_header_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["latestAcceptedPurchaseOrderAddressGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_address_header_witness_input_count_drift(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        manifest["latestAcceptedPurchaseOrderAddressGraph"]["inputCount"] = 68
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)

    def test_exact_successor_inventory_drift_is_rejected(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        reviewed = guard.tracked_inputs(guard.ROOT)
        for mutation in ("change", "remove", "add"):
            with self.subTest(mutation=mutation):
                mutated = copy.deepcopy(manifest)
                inventory = mutated["intentionalSourceChanges"]["reviewedInputs"]
                path = next(iter(inventory))
                if mutation == "change":
                    inventory[path] = "100644 blob drift"
                elif mutation == "remove":
                    del inventory[path]
                else:
                    inventory["Legacy.Maliev.ProcurementService.Api/Unreviewed.cs"] = "100644 blob added"
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, mutated)


    def test_current_graph_rejects_file_metadata_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["latestAcceptedFileMetadataGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)

    def test_current_graph_rejects_file_metadata_witness_input_count_drift(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        manifest["latestAcceptedFileMetadataGraph"]["inputCount"] = 69
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)


    def test_current_graph_rejects_supplier_identity71_witness_and_preimage_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path", "sha256", "procurement", "gitBlob"):
            with self.subTest(field=field):
                changed = copy.deepcopy(manifest)
                changed["latestAcceptedSupplierIdentityGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                changed = copy.deepcopy(manifest)
                changed["intentionalSourceChanges"]["changedInputs"][path]["previousMetadata"] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)

    def test_current_graph_rejects_supplier_identity71_and_current72_count_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for source, field, value in (("latestAcceptedSupplierIdentityGraph","inputCount",70),
                                     ("intentionalSourceChanges","inputCount",71),
                                     ("intentionalSourceChanges","unchangedInputCount",68),
                                     ("intentionalSourceChanges","reviewedProcurement","main"),
                                     ("intentionalSourceChanges","reviewedTree","0"*40)):
            with self.subTest(source=source,field=field):
                changed = copy.deepcopy(manifest)
                changed[source][field] = value
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)


    def test_current_graph_rejects_metadata_identity72_witness_custody_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field, value in (("path", "drift"), ("sha256", "0"*64), ("gitBlob", "0"*40),
                             ("procurement", "main"), ("inputCount", 71)):
            with self.subTest(field=field):
                changed = copy.deepcopy(manifest)
                changed["latestAcceptedMetadataIdentityGraph"][field] = value
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)

    def test_current_graph_rejects_header72_one_delta71_unchanged_envelope_drift(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field, value in (("acceptedBase", "main"), ("previousProcurement", "main"),
                             ("inputCount", 71), ("unchangedInputCount", 69),
                             ("reviewedProcurement", "main"), ("reviewedTree", "0"*40)):
            with self.subTest(field=field):
                changed = copy.deepcopy(manifest)
                changed["intentionalSourceChanges"][field] = value
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)
        changed = copy.deepcopy(manifest)
        changed["previousMetadataIdentityIntentionalSourceChanges"]["unchangedInputCount"] = 1
        with self.assertRaises(ValueError):
            guard.require_historical_graph(changed)



    def test_exact_two_source_changes_preserve_seventy_other_runtime_inputs(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        change = manifest["previousHeaderContactIntentionalSourceChanges"]
        self.assertEqual(72,change["inputCount"])
        self.assertEqual(70,change["unchangedInputCount"])
        self.assertEqual({
            "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs",
            "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs",
        },set(change["changedInputs"]))
        guard.require_historical_graph(manifest)



    def test_supplier_audit_successor_has_one_change_and_seventy_one_retained_inputs(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        change = manifest["previousSupplierAuditIntentionalSourceChanges"]
        self.assertEqual((72,71),(change["inputCount"],change["unchangedInputCount"]))
        self.assertEqual({"Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"},
                         set(change["changedInputs"]))
        guard.require_historical_graph(manifest)

    def test_header_contact_witness_custody_cannot_be_rebound(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path","sha256","gitBlob","procurement","inputCount","acceptedMain","acceptedReceipt"):
            changed = copy.deepcopy(manifest)
            changed["latestAcceptedHeaderContactGraph"][field] = "drift"
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.require_historical_graph(changed)


    def test_metadata_audit_successor_has_one_change_and_seventy_one_retained_inputs(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        change = manifest["intentionalSourceChanges"]
        self.assertEqual((72,71),(change["inputCount"],change["unchangedInputCount"]))
        self.assertEqual({"Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"},
                         set(change["changedInputs"]))
        guard.require_historical_graph(manifest)

    def test_supplier_audit_witness_custody_cannot_be_rebound(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in ("path","sha256","gitBlob","procurement","inputCount","acceptedMain","acceptedReceipt"):
            changed = copy.deepcopy(manifest)
            changed["latestAcceptedSupplierAuditGraph"][field] = "drift"
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.require_historical_graph(changed)


if __name__ == "__main__":
    unittest.main()
