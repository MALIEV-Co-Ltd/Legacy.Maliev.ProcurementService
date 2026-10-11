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
        from unittest.mock import patch
        historical_manifest=original_root / "tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-journal.json"
        manifest_patch=patch.object(guard, "MANIFEST", historical_manifest)
        manifest_patch.start();self.addCleanup(manifest_patch.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        committed_root = pathlib.Path(temporary.name)
        for source in (original_root / "tools/ProcurementAuthProgram.Tests").glob("public-graph*.json"):
            relative = source.relative_to(original_root)
            if source.name == "public-graph-fixture-owner-correlation.json":
                continue
            raw = subprocess.check_output(["git", "-C", str(SOURCE_REPO), "show", "HEAD:" + relative.as_posix()], timeout=15)
            target = committed_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        replacement = patch.object(guard, "ROOT", committed_root)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.reviewed = {project + "/Input.cs": "100644 blob reviewed" for project in guard.PROJECTS}
        for path in guard.FIXTURE_INPUTS:
            self.reviewed[path] = "100644 blob fixture"

    def historical_inputs(self):
        # Immutable predecessor source map, not native validation evidence.
        selected = {path: value for path, value in guard.FROZEN_OWNER_INPUT_METADATA.items()
                    if path not in guard.FIXTURE_INPUTS or path in (guard.FIXTURE, guard.JOURNAL, guard.JOURNAL_CONTROLS)}
        selected[guard.FIXTURE] = guard.FROZEN_OWNER_SOURCE_CHANGE["changedInputs"][guard.FIXTURE]["previousMetadata"]
        return selected

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

    def test_missing_journal_helper_or_controls_is_rejected_even_when_equal(self):
        for path in (guard.JOURNAL, guard.JOURNAL_CONTROLS):
            with self.subTest(path=path):
                reviewed = dict(self.reviewed)
                del reviewed[path]
                with self.assertRaises(ValueError):
                    guard.require_equal(reviewed, reviewed)

    def test_previous_startup_graph_custody_and_eol_are_immutable(self):
        import copy
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for field in manifest["previousReviewedStartupDiagnosticGraph"]:
            with self.subTest(field=field):
                mutated = copy.deepcopy(manifest)
                mutated["previousReviewedStartupDiagnosticGraph"][field] = "drift"
                with self.assertRaises(ValueError):
                    guard.require_historical_graph(mutated)
        source = guard.ROOT / manifest["previousReviewedStartupDiagnosticGraph"]["path"]
        source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
        with self.assertRaises(ValueError):
            guard.require_historical_graph(manifest)


    def test_frozen_literal_changes_keep_other_runtime_inputs(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        guard.require_source_change(self.historical_inputs(), manifest)

    def test_unrelated_drift_is_rejected_even_when_witness_agrees(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        reviewed = self.historical_inputs()
        unchanged = next(path for path in reviewed if path not in manifest["intentionalSourceChanges"]["changedInputs"])
        reviewed[unchanged] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_query_blob_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        reviewed = self.historical_inputs()
        reviewed[next(iter(manifest["intentionalSourceChanges"]["changedInputs"]))] = "100644 blob unrelated"
        with self.assertRaises(ValueError):
            guard.require_source_change(reviewed, manifest)

    def test_each_reviewed_changed_input_drift_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = self.historical_inputs()
                reviewed[path] = "100644 blob unrelated"
                with self.assertRaises(ValueError):
                    guard.require_source_change(reviewed, manifest)

    def test_each_missing_reviewed_changed_input_is_rejected(self):
        import json
        manifest = json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
        for path in manifest["intentionalSourceChanges"]["changedInputs"]:
            with self.subTest(path=path):
                reviewed = self.historical_inputs()
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



# Source-only controls use immutable Git bytes and temporary simulated baseline scopes.
from pathlib import Path
import copy, hashlib, json, os, subprocess
from unittest.mock import patch
SOURCE_REPO=Path(os.environ.get("OWNER_GUARD_SOURCE_REPO", str(Path(__file__).resolve().parents[1])))
def source_bytes(path, ref="HEAD"):
    return subprocess.check_output(["git", "-C", str(SOURCE_REPO), "show", ref+":"+path], timeout=15)
class AuthOwnerControls(unittest.TestCase):
 def setUp(self):
  self.original_root=guard.ROOT;self.original_producer=guard.REVIEWED_CORRELATION_PRODUCER
  import tempfile
  temporary=tempfile.TemporaryDirectory(prefix='owner-graph-source-control-');self.addCleanup(temporary.cleanup)
  guard.ROOT=Path(temporary.name);guard.REVIEWED_CORRELATION_PRODUCER='a'*40
  for entry in (SOURCE_REPO/'tools/ProcurementAuthProgram.Tests').glob('public-graph*.json'):
   if entry.name=='public-graph-fixture-owner-correlation.json':continue
   relative=entry.relative_to(SOURCE_REPO);target=guard.ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source_bytes(relative.as_posix()))
  self.addCleanup(setattr,guard,'ROOT',self.original_root);self.addCleanup(setattr,guard,'REVIEWED_CORRELATION_PRODUCER',self.original_producer)
  self.graph=json.loads(guard.MANIFEST.read_text(encoding='utf-8'))
  for ref in self.graph['references']:
   if ref['repository']=='Legacy.Maliev.ProcurementService':ref['commit']='a'*40
  self.graph['ownerCorrelationSourceBinding']['reviewedProducer']='a'*40;self.graph['ownerCorrelationSourceBinding']['releaseAllowed']=True
  self.graph['intentionalSourceChanges']['reviewedProcurement']='a'*40
  self.inputs=dict(guard.FROZEN_OWNER_INPUT_METADATA)
 def test_actual_bound_producer_graph_and_git80_pass(self):
  guard.REVIEWED_CORRELATION_PRODUCER=self.original_producer
  graph=json.loads(guard.MANIFEST.read_text(encoding="utf-8"))
  guard.require_owner_graph(graph)
  actual=guard.tracked_inputs(SOURCE_REPO)
  guard.require_owner_inputs(actual,actual,graph)
 def test_exact80_graph_and_metadata_positive_source_control(self):
  guard.require_owner_graph(self.graph);guard.require_owner_inputs(self.inputs,self.inputs,self.graph)
 def test_unbound_real_draft_is_rejected_before_admission(self):
  guard.REVIEWED_CORRELATION_PRODUCER=None
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_mutable_or_noncanonical_producer_rejected(self):
  for value in ['main','A'*40,'not-a-sha']:
   guard.REVIEWED_CORRELATION_PRODUCER=value
   with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_false_release_flag_rejected(self):
  self.graph['ownerCorrelationSourceBinding']['releaseAllowed']=False
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_producer_reference_drift_rejected(self):
  self.graph['references'][-1]['commit']='b'*40
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_external_reference_drift_rejected(self):
  self.graph['references'][0]['commit']='b'*40
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_auth15_case_drift_rejected(self):
  self.graph['expectedCases']=16
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_auth15_method_drift_rejected(self):
  self.graph['expectedMethods']['unknown.method']=1
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_authority_widening_rejected(self):
  for field in ['productionEnrollmentProven','productionIamBridgeProven','wholeInitialSourceParityClosed']:
   graph=copy.deepcopy(self.graph);graph[field]=True
   with self.assertRaises(ValueError):guard.require_owner_graph(graph)
 def test_predecessor69_sha_drift_rejected(self):
  self.graph['previousReviewedStartupJournalGraph']['sha256']='0'*64
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_graph_unknown_or_missing_field_rejected(self):
  graph=copy.deepcopy(self.graph);graph['unknownField']=True
  with self.assertRaises(ValueError):guard.require_owner_graph(graph)
  del self.graph['ownerCorrelationSourceBinding']
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_source_change_metadata_drift_rejected(self):
  self.graph['intentionalSourceChanges']['changedInputs'][guard.FIXTURE]['previousMetadata']='forged'
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_66_digest_drift_rejected(self):
  self.graph['intentionalSourceChanges']['productionBuildInputSha256']='0'*64
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_preserved_predecessor_annotation_drift_rejected(self):
  self.graph['fixtureEnrollment']='forged'
  with self.assertRaises(ValueError):guard.require_owner_graph(self.graph)
 def test_any_missing_explicit_path_rejected_even_if_both_maps_agree(self):
  for path in guard.FIXTURE_INPUTS:
   current=dict(self.inputs);del current[path]
   with self.assertRaises(ValueError):guard.require_owner_inputs(current,current,self.graph)
 def test_each_source_blob_drift_rejected_even_if_both_maps_agree(self):
  for path in guard.FIXTURE_INPUTS:
   current=dict(self.inputs);current[path]='100644 blob '+'0'*40
   with self.assertRaises(ValueError):guard.require_owner_inputs(current,current,self.graph)
 def test_added_selected_path_rejected(self):
  current=dict(self.inputs);current['Legacy.Maliev.ProcurementService.Api/Added.cs']='100644 blob '+'0'*40
  with self.assertRaises(ValueError):guard.require_owner_inputs(current,current,self.graph)
 def test_production_blob_drift_rejected(self):
  current=dict(self.inputs);path=next(path for path in current if path not in guard.FIXTURE_INPUTS);current[path]='100644 blob '+'0'*40
  with self.assertRaises(ValueError):guard.require_owner_inputs(current,current,self.graph)
 def test_selection_rule_picks_exact80_and_not_unattributed_test_tree(self):
  records=[(metadata+'\t'+path).encode()+b'\0' for path,metadata in self.inputs.items()]
  records.append(('100644 blob '+'0'*40+'\tLegacy.Maliev.ProcurementService.Tests/Integration/Unselected.cs').encode()+b'\0')
  with patch.object(guard.subprocess,'check_output',return_value=b''.join(records)):
   self.assertEqual(self.inputs,guard.tracked_inputs(Path('unit-only-no-native-checkout')))


if __name__ == "__main__":
    unittest.main()
