"""Mutation controls for immutable runtime/public-fixture admission."""
import importlib.util
import pathlib
import unittest
from test_procurement_address_null_consumer import AddressNullConsumerControls

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

        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        for path in producer:
            with self.subTest(consumer_input=path):
                changed = guard.tracked_inputs(guard.ROOT)
                changed[path] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_consumer_inputs(changed, producer, manifest)


    def test_added_runtime_input_is_rejected(self):
        current = dict(self.reviewed)
        current[guard.PROJECTS[0] + "/Added.cs"] = "100644 blob added"
        with self.assertRaises(ValueError):
            guard.require_equal(current, self.reviewed)

        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        changed = guard.tracked_inputs(guard.ROOT)
        changed[guard.PROJECTS[0] + "/Added.cs"] = "100644 blob added"
        with self.assertRaises(ValueError):
            guard.require_consumer_inputs(changed, producer, manifest)


    def test_missing_runtime_project_is_rejected_even_when_equal(self):
        reviewed = dict(self.reviewed)
        del reviewed[guard.PROJECTS[3] + "/Input.cs"]
        with self.assertRaises(ValueError):
            guard.require_equal(reviewed, reviewed)

        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        for path in producer:
            with self.subTest(missing_consumer_input=path):
                changed = guard.tracked_inputs(guard.ROOT)
                del changed[path]
                with self.assertRaises(ValueError):
                    guard.require_consumer_inputs(changed, producer, manifest)


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
        guard.require_source_change(dict(manifest["intentionalSourceChanges"]["reviewedInputs"]), manifest)

        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        guard.require_consumer_inputs(guard.tracked_inputs(guard.ROOT), producer, manifest)


    def test_unrelated_drift_is_rejected_even_when_witness_agrees(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = dict(manifest["intentionalSourceChanges"]["reviewedInputs"])
        unchanged = next(path for path in reviewed if path not in manifest["intentionalSourceChanges"]["changedInputs"])
        reviewed[unchanged] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_query_blob_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text())
        reviewed = dict(manifest["intentionalSourceChanges"]["reviewedInputs"])
        reviewed[next(iter(manifest["intentionalSourceChanges"]["changedInputs"]))] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_each_reviewed_changed_input_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = dict(manifest["intentionalSourceChanges"]["reviewedInputs"])
                reviewed[path] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_each_missing_reviewed_changed_input_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = dict(manifest["intentionalSourceChanges"]["reviewedInputs"])
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

        import copy
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        binding = manifest["supplierExplicitSizeConsumer"]
        for field in binding:
            with self.subTest(consumer_custody=field):
                changed = copy.deepcopy(manifest)
                changed["supplierExplicitSizeConsumer"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_consumer_binding(changed)
        for authority in ("producerHarness", "consumerHarness"):
            for field in ("path", "gitBlob"):
                with self.subTest(authority=authority, field=field):
                    changed = copy.deepcopy(manifest)
                    changed["supplierExplicitSizeConsumer"][authority][field] = ""
                    with self.assertRaises(ValueError):
                        guard.require_consumer_binding(changed)
                    del changed["supplierExplicitSizeConsumer"][authority][field]
                    with self.assertRaises(ValueError):
                        guard.require_consumer_binding(changed)
        changed = copy.deepcopy(manifest)
        changed["supplierExplicitSizeConsumer"]["consumerHarness"] = copy.deepcopy(binding["producerHarness"])
        with self.assertRaises(ValueError):
            guard.require_consumer_binding(changed)


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

        from unittest import mock
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = guard.ROOT / ".joined-public/Legacy.Maliev.ProcurementService"
        binding = manifest["supplierExplicitSizeConsumer"]

        def exact_output(arguments, **kwargs):
            repository = pathlib.Path(arguments[2])
            command = tuple(arguments[3:])
            if repository == producer and command == ("rev-parse", "HEAD"):
                return binding["producerCommit"] + "\n"
            authority = "consumerHarness" if repository == guard.ROOT else "producerHarness"
            return binding[authority]["gitBlob"] + "\n"

        with mock.patch.object(guard.subprocess, "check_output", side_effect=exact_output) as calls:
            guard.require_harness_custody(guard.ROOT, producer, manifest)
            self.assertEqual(5, calls.call_count)
        for local_root, producer_root in ((producer, guard.ROOT), (guard.ROOT, guard.ROOT),
                                          (guard.ROOT / "other", producer), (guard.ROOT, producer / "other")):
            with self.subTest(local_root=local_root, producer_root=producer_root), self.assertRaises(ValueError):
                guard.require_harness_custody(local_root, producer_root, manifest)
        for corrupt_index in range(5):
            with self.subTest(corrupt_git_observation=corrupt_index):
                observations = [
                    binding["producerCommit"] + "\n",
                    binding["consumerHarness"]["gitBlob"] + "\n",
                    binding["consumerHarness"]["gitBlob"] + "\n",
                    binding["producerHarness"]["gitBlob"] + "\n",
                    binding["producerHarness"]["gitBlob"] + "\n",
                ]
                for invalid in ("", "0" * 40 + "\n",
                                (binding["producerHarness"] if corrupt_index in (1, 2)
                                 else binding["consumerHarness"])["gitBlob"] + "\n"):
                    changed = list(observations)
                    changed[corrupt_index] = invalid
                    with mock.patch.object(guard.subprocess, "check_output", side_effect=changed):
                        with self.assertRaises(ValueError):
                            guard.require_harness_custody(guard.ROOT, producer, manifest)


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
        reviewed = dict(manifest["intentionalSourceChanges"]["reviewedInputs"])
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
                             ("inputCount", 71), ("unchangedInputCount", 68),
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
        change = manifest["previousMetadataAuditIntentionalSourceChanges"]
        self.assertEqual((72,71),(change["inputCount"],change["unchangedInputCount"]))
        self.assertEqual({"Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"},
                         set(change["changedInputs"]))
        current = manifest["previousCountryIdIntentionalSourceChanges"]
        self.assertEqual((72,71),(current["inputCount"],current["unchangedInputCount"]))
        self.assertEqual(set(change["changedInputs"]),set(current["changedInputs"]))
        successor = manifest["previousSourceBodyIntentionalSourceChanges"]
        self.assertEqual((74,69),(successor["inputCount"],successor["unchangedInputCount"]))
        self.assertEqual(set(json.loads('["Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementSourceBodyInputFormatter.cs","Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementOriginalBodyModels.cs","Legacy.Maliev.ProcurementService.Api/Program.cs","Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj","Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"]')),set(successor["changedInputs"]))
        added = {path for path, binding in successor["changedInputs"].items() if binding["previousMetadata"] is None}
        self.assertEqual(2,len(added))
        supplier = manifest["intentionalSourceChanges"]
        self.assertEqual((74,71),(supplier["inputCount"],supplier["unchangedInputCount"]))
        self.assertEqual(set(json.loads('["Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs","Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs","Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"]')),set(supplier["changedInputs"]))
        guard.require_historical_graph(manifest)

    def test_supplier_audit_witness_custody_cannot_be_rebound(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for witness in ("latestAcceptedSupplierAuditGraph", "latestAcceptedMetadataAuditGraph", "latestAcceptedCountryIdGraph"):
            for field in ("path","sha256","gitBlob","procurement","inputCount","acceptedMain","acceptedReceipt"):
                changed = copy.deepcopy(manifest)
                changed[witness][field] = "drift"
                with self.subTest(witness=witness,field=field), self.assertRaises(ValueError):
                    guard.require_historical_graph(changed)


    def test_exact_observation_consumer_transition_rejects_old_missing_and_unknown_program(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        producer = manifest["intentionalSourceChanges"]["reviewedInputs"]
        current = guard.tracked_inputs(guard.ROOT)
        guard.require_consumer_inputs(current, producer, manifest)
        program = "Legacy.Maliev.ProcurementService.Api/Program.cs"
        for metadata in ("100644 blob 70310b7db68e08366ee3c723211cdd3910c03f9f", "100644 blob " + "0" * 40, None):
            changed = dict(current)
            if metadata is None:
                del changed[program]
            else:
                changed[program] = metadata
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                guard.require_consumer_inputs(changed, producer, manifest)
        for metadata in ("100644 blob a82fb0b60ca92d2df1a39a3b82eaecdeef1f7505", "100644 blob " + "0" * 40, None):
            changed = dict(producer)
            if metadata is None:
                del changed[program]
            else:
                changed[program] = metadata
            with self.subTest(preimage=metadata), self.assertRaises(ValueError):
                guard.observation_consumer_inputs(changed)



if __name__ == "__main__":
    unittest.main()
