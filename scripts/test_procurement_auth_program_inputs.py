"""Mutation controls for immutable runtime/public-fixture admission."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("join_guard", pathlib.Path(__file__).with_name("verify-procurement-auth-program.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
ACTIVE_MANIFEST = guard.MANIFEST
ORIGINAL_DIAGNOSTIC_PRODUCER = guard.DIAGNOSTIC_PRODUCER


def inactive_source_graph():
    # Runtime callers cannot downgrade. These controls exercise the immutable
    # producer's inactive graph after current source admission becomes active.
    if ORIGINAL_DIAGNOSTIC_PRODUCER is None:
        return guard.strict_json(ACTIVE_MANIFEST.read_bytes())
    return guard.strict_json(source_bytes(
        'tools/ProcurementAuthProgram.Tests/public-graph-fixture-owner-correlation.json',
        ORIGINAL_DIAGNOSTIC_PRODUCER))

ORIGINAL_PREDECESSOR_BYTES = (guard.ROOT / guard.OWNER_PREDECESSOR_PATH).read_bytes()
guard.MANIFEST = guard.ROOT / guard.OWNER_PREDECESSOR_PATH


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
            if source.name in ("public-graph-fixture-owner-correlation.json", "public-graph-fixture-owner-correlation-v1.json"):
                continue
            raw = subprocess.check_output(["git", "-C", str(SOURCE_REPO), "show", "HEAD:" + relative.as_posix()], timeout=15)
            target = committed_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        predecessor = committed_root / guard.OWNER_PREDECESSOR_PATH
        predecessor.parent.mkdir(parents=True, exist_ok=True)
        predecessor.write_bytes(ORIGINAL_PREDECESSOR_BYTES)
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
  self.addCleanup(setattr,guard,'ROOT',self.original_root);self.addCleanup(setattr,guard,'REVIEWED_CORRELATION_PRODUCER',self.original_producer)
  for entry in (SOURCE_REPO/'tools/ProcurementAuthProgram.Tests').glob('public-graph*.json'):
   if entry.name in ('public-graph-fixture-owner-correlation.json', 'public-graph-fixture-owner-correlation-v1.json'):continue
   relative=entry.relative_to(SOURCE_REPO);target=guard.ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source_bytes(relative.as_posix()))
  (guard.ROOT/guard.OWNER_PREDECESSOR_PATH).write_bytes(ORIGINAL_PREDECESSOR_BYTES)
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
  actual=guard.tracked_inputs(SOURCE_REPO, guard.REVIEWED_CORRELATION_PRODUCER)
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



# Every positive producer below is a real temporary Git commit, not a proposed pin.
import contextlib
import io
import shutil
import tempfile


class DiagnosticDependencyControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='auth82-real-git-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.owned = cls.base / 'owned'
        cls.owned.mkdir()
        cls.joined = cls.base / 'joined'
        cls.joined.mkdir()
        cls.custody_root = guard.ROOT

        def command(path, *args):
            return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.PIPE, timeout=15).decode().strip()
        cls.git = staticmethod(command)
        command(cls.owned, 'init', '-q')
        command(cls.owned, 'config', 'core.autocrlf', 'false')
        command(cls.owned, 'config', 'gc.auto', '0')
        command(cls.owned, 'config', 'user.name', 'Source Control Fixture')
        command(cls.owned, 'config', 'user.email', 'source-control@example.invalid')
        for path in guard.FROZEN_OWNER_INPUT_METADATA:
            target = cls.owned / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes(path))
        diagnostic_root = Path(os.environ.get('AUTH_GUARD_DIAGNOSTIC_SOURCE', str(SOURCE_REPO)))
        for path in (guard.DIAGNOSTIC_PATHS[-2], guard.DIAGNOSTIC_PATHS[-1],
                     'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs'):
            target = cls.owned / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((diagnostic_root / path).read_bytes())
        for source in (cls.custody_root / 'tools/ProcurementAuthProgram.Tests').glob('public-graph*.json'):
            target = cls.owned / source.relative_to(cls.custody_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.name in ('public-graph-fixture-owner-correlation.json', 'public-graph-fixture-owner-correlation-v1.json'):
                # Active/uncommitted successor and exact separately captured predecessor.
                target.write_bytes(source.read_bytes())
            else:
                # Frozen historical custody comes from real committed Git bytes,
                # never Windows CRLF working bytes or normalized historical content.
                target.write_bytes(source_bytes(source.relative_to(cls.custody_root).as_posix()))
        command(cls.owned, 'add', '--all')
        command(cls.owned, 'commit', '-q', '-m', 'Temporary real source producer for guard controls')
        cls.producer = command(cls.owned, 'rev-parse', 'HEAD')
        cls.metadata = guard.diagnostic_tracked_inputs(cls.owned)
        cls.graph = copy.deepcopy(guard.FROZEN_DIAGNOSTIC_GRAPH)
        for entry in cls.graph['references']:
            if entry['repository'] == 'Legacy.Maliev.ProcurementService':
                entry['commit'] = cls.producer
        binding = cls.graph['diagnosticDependencySourceBinding']
        binding.update(reviewedProducer=cls.producer, releaseAllowed=True, inputMetadata=cls.metadata)
        changed = {path: {'previousMetadata': guard.FROZEN_OWNER_INPUT_METADATA.get(path),
                         'reviewedMetadata': value, 'classification': 'Test-only diagnostic dependency; no native qualification'}
                   for path, value in cls.metadata.items() if guard.FROZEN_OWNER_INPUT_METADATA.get(path) != value}
        unchanged = {path: value for path, value in cls.metadata.items() if path not in changed}
        cls.graph['intentionalSourceChanges'].update(reviewedProcurement=cls.producer, changedInputs=changed,
            unchangedInputCount=len(unchanged), unchangedInputSha256=hashlib.sha256(json.dumps(unchanged, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        # A private Git repository can read existing local immutable objects through
        # an alternate without changing the source repository, refs or working files.
        reference_root = Path(os.environ.get('AUTH_GUARD_REFERENCE_ROOT', str(SOURCE_REPO / '.joined-public')))
        for entry in cls.graph['references']:
            target = cls.joined / entry['repository']
            target.mkdir()
            command(target, 'init', '-q')
            source = cls.owned if entry['repository'] == 'Legacy.Maliev.ProcurementService' else reference_root / entry['repository']
            command(source, 'cat-file', '-e', entry['commit'] + '^{commit}')
            objects = command(source, 'rev-parse', '--path-format=absolute', '--git-path', 'objects')
            (target / '.git/objects/info/alternates').write_bytes((objects.replace('\\', '/') + '\n').encode('utf-8'))
            command(target, 'config', 'core.autocrlf', 'false')
            command(target, 'config', 'gc.auto', '0')
            command(target, 'update-ref', 'HEAD', entry['commit'])
            if entry['repository'] == 'Legacy.Maliev.ProcurementService':
                command(target, 'reset', '--hard', entry['commit'])
        (cls.owned / 'source-control-admission.txt').write_text('Real temporary admission descendant\n', encoding='utf-8')
        command(cls.owned, 'add', '--all')
        command(cls.owned, 'commit', '-q', '-m', 'Temporary actual admission descendant')
        cls.source = command(cls.owned, 'rev-parse', 'HEAD')
        (cls.owned / 'source-control-head.txt').write_text('Real temporary owned descendant\n', encoding='utf-8')
        command(cls.owned, 'add', '--all')
        command(cls.owned, 'commit', '-q', '-m', 'Temporary actual owned descendant')
        cls.head = command(cls.owned, 'rev-parse', 'HEAD')
        custody_location = os.environ.get('AUTH_GUARD_GIT_CUSTODY_ROOT')
        if custody_location:
            custody = Path(custody_location)
            custody.mkdir(parents=True, exist_ok=False)
            objects = []
            commands = []
            def observed_git(*arguments, payload=None):
                observed = subprocess.run(['git', '-C', str(cls.owned), *arguments], input=payload,
                                          capture_output=True, timeout=15)
                commands.append({'arguments': list(arguments), 'exitCode': observed.returncode,
                                 'stdoutSha256': hashlib.sha256(observed.stdout).hexdigest(),
                                 'stderrSha256': hashlib.sha256(observed.stderr).hexdigest()})
                observed.check_returncode()
                return observed.stdout
            for label, commit in (('P', cls.producer), ('S', cls.source), ('H', cls.head)):
                raw = observed_git('cat-file', 'commit', commit)
                tree = observed_git('rev-parse', commit + '^{tree}').decode().strip()
                parents = observed_git('show', '-s', '--format=%P', commit).decode().strip().split()
                raw_tree = observed_git('cat-file', 'tree', tree)
                commit_hash = observed_git('hash-object', '-t', 'commit', '--stdin', payload=raw).decode().strip()
                tree_hash = observed_git('hash-object', '-t', 'tree', '--stdin', payload=raw_tree).decode().strip()
                if commit_hash != commit or tree_hash != tree:
                    raise RuntimeError('Actual Git object identity mismatch')
                (custody / (label + '.commit.raw')).write_bytes(raw)
                (custody / (label + '.tree.raw')).write_bytes(raw_tree)
                selected_raw = observed_git('ls-tree', '-r', '-z', commit)
                (custody / (label + '.ls-tree.raw')).write_bytes(selected_raw)
                objects.append({'role': label, 'commit': commit, 'tree': tree, 'parents': parents,
                                'commitRawSha256': hashlib.sha256(raw).hexdigest(),
                                'treeRawSha256': hashlib.sha256(raw_tree).hexdigest(),
                                'actualHashObjectCommit': commit_hash, 'actualHashObjectTree': tree_hash})
            for before, after in ((cls.producer, cls.source), (cls.source, cls.head)):
                observed_git('merge-base', '--is-ancestor', before, after)
            blobs = {}
            for path, metadata in cls.metadata.items():
                raw = observed_git('show', cls.producer + ':' + path)
                blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
                if blob != metadata.rsplit(' ', 1)[1]:
                    raise RuntimeError('Actual selected blob identity mismatch')
                blobs[path] = {'metadata': metadata, 'gitBlob': blob, 'rawSha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            (custody / 'actual-control-graph.json').write_text(json.dumps(cls.graph, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            (custody / 'custody.json').write_text(json.dumps({'scope': 'Temporary actual Git source controls ONLY; never a production producer',
                'objects': objects, 'commands': commands, 'selectedBlobs': blobs,
                'temporaryRoot': str(cls.base), 'selectedCount': len(blobs), 'productionCount': 66,
                'productionDigest': guard.PRODUCTION_BUILD_SHA256, 'nativeExecuted': False, 'qualification': False}, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    def setUp(self):
        self.graph = copy.deepcopy(type(self).graph)
        for name, value in [('ROOT', self.owned), ('DIAGNOSTIC_PRODUCER', self.producer), ('FROZEN_DIAGNOSTIC_GRAPH', copy.deepcopy(self.graph))]:
            replacement = patch.object(guard, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def reject_in_both_paths(self, graph):
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            guard.inputs(self.joined, graph, owned_head=self.head, source_head=self.source)
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            guard.results(self.base / 'absent-results', graph, joined_root=self.joined, owned_head=self.head, source_head=self.source)

    def test_auth_owner_setup_skips_uncommitted_predecessor_and_restores_scope(self):
        previous_root, previous_producer = guard.ROOT, guard.REVIEWED_CORRELATION_PRODUCER
        control = AuthOwnerControls('test_exact80_graph_and_metadata_positive_source_control')
        try:
            control.setUp()
            self.assertEqual(ORIGINAL_PREDECESSOR_BYTES, (guard.ROOT / guard.OWNER_PREDECESSOR_PATH).read_bytes())
        finally:
            control.doCleanups()
        self.assertEqual(previous_root, guard.ROOT)
        self.assertEqual(previous_producer, guard.REVIEWED_CORRELATION_PRODUCER)

    def test_auth_owner_failed_setup_restores_scope_and_producer(self):
        previous_root, previous_producer = guard.ROOT, guard.REVIEWED_CORRELATION_PRODUCER
        control = AuthOwnerControls('test_exact80_graph_and_metadata_positive_source_control')
        try:
            with patch(__name__ + '.source_bytes', side_effect=RuntimeError('Controlled Git custody read failure')):
                with self.assertRaises(RuntimeError):
                    control.setUp()
        finally:
            control.doCleanups()
        self.assertEqual(previous_root, guard.ROOT)
        self.assertEqual(previous_producer, guard.REVIEWED_CORRELATION_PRODUCER)

    def test_real_git82_producer_source_head_and_selected_bytes_pass(self):
        self.assertEqual(82, len(self.metadata))
        with contextlib.redirect_stdout(io.StringIO()):
            guard.inputs(self.joined, self.graph, owned_head=self.head, source_head=self.source)

    def test_real_git_historical80_selection_remains_exact(self):
        actual = guard.tracked_inputs(SOURCE_REPO, guard.REVIEWED_CORRELATION_PRODUCER)
        self.assertEqual(80, len(actual))
        guard.require_owner_inputs(actual, actual, guard.frozen_historical_graph())

    def test_real_git_results_path_uses_same_admission(self):
        results = self.base / 'actual-method-count-results'
        results.mkdir(exist_ok=True)
        ns = 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'
        import xml.etree.ElementTree as ET
        document = ET.Element('{' + ns + '}TestRun')
        definitions = ET.SubElement(document, '{' + ns + '}TestDefinitions')
        rows = ET.SubElement(document, '{' + ns + '}Results')
        number = 0
        for method, count in self.graph['expectedMethods'].items():
            class_name, name = method.rsplit('.', 1)
            for _ in range(count):
                number += 1
                unit = ET.SubElement(definitions, '{' + ns + '}UnitTest', id=str(number))
                ET.SubElement(unit, '{' + ns + '}TestMethod', className=class_name, name=name)
                ET.SubElement(rows, '{' + ns + '}UnitTestResult', testId=str(number), outcome='Passed')
        summary = ET.SubElement(document, '{' + ns + '}ResultSummary')
        ET.SubElement(summary, '{' + ns + '}Counters', total=str(number), passed=str(number), failed='0')
        ET.ElementTree(document).write(results / 'source-control.trx', encoding='utf-8')
        coverage = ET.Element('coverage')
        packages = ET.SubElement(coverage, 'packages')
        for name in ('Legacy.Maliev.AuthService.Api', 'Legacy.Maliev.ProcurementService.Api'):
            package = ET.SubElement(packages, 'package', name=name)
            line = ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(package, 'classes'), 'class'), 'lines'), 'line', number='1', hits='1')
        ET.ElementTree(coverage).write(results / 'coverage.cobertura.xml', encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            guard.results(results, self.graph, joined_root=self.joined, owned_head=self.head, source_head=self.source)
        # These fabricated method/count reports exercise parsing, not native proof.
        self.assertEqual(15, number)

    def test_inactive_source_schema_passes_but_inputs_results_reject(self):
        inactive = inactive_source_graph()
        with patch.object(guard, 'DIAGNOSTIC_PRODUCER', None), patch.object(guard, 'FROZEN_DIAGNOSTIC_GRAPH', inactive):
            guard.require_diagnostic_graph(inactive, source_only=True)
            self.reject_in_both_paths(inactive)

    def test_current_total82_as_float_rejected(self):
        self.graph['diagnosticDependencySourceBinding']['inputCount'] = 82.0
        self.reject_in_both_paths(self.graph)

    def test_auth_count15_as_float_rejected(self):
        self.graph['expectedCases'] = 15.0
        self.reject_in_both_paths(self.graph)

    def test_boolean_integer_substitutions_rejected(self):
        for field, value in [('releaseAllowed', 1), ('fixtureInputCount', True), ('productionBuildInputCount', 66.0), ('reviewedProducer', False)]:
            with self.subTest(field=field):
                graph = copy.deepcopy(self.graph)
                graph['diagnosticDependencySourceBinding'][field] = value
                self.reject_in_both_paths(graph)

    def test_historical_total80_as_float_and_method_counts_rejected(self):
        graph = guard.frozen_historical_graph()
        for field in ('inputCount', 'productionBuildInputCount'):
            changed = copy.deepcopy(graph)
            changed['intentionalSourceChanges'][field] = float(changed['intentionalSourceChanges'][field])
            self.reject_in_both_paths(changed)
        graph['expectedCases'] = 15.0
        self.reject_in_both_paths(graph)

    def test_nonfinite_duplicate_keys_and_numeric_overflow_rejected(self):
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}', '{"x":1,"x":1}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                guard.strict_json(text)
        for value in (float('nan'), float('inf'), float('-inf')):
            graph = copy.deepcopy(self.graph)
            graph['expectedCases'] = value
            self.reject_in_both_paths(graph)

    def test_nested_predecessor_metadata_type_drift_rejected(self):
        self.graph['previousReviewedOwnerCorrelationGraph']['inputCount'] = 80.0
        self.reject_in_both_paths(self.graph)

    def test_unknown_missing_keys_and_mixed_schema_rejected(self):
        for mutate in (lambda graph: graph.update(extra=True), lambda graph: graph.pop('schemaVersion'), lambda graph: graph.update(schemaVersion=1)):
            graph = copy.deepcopy(self.graph)
            mutate(graph)
            self.reject_in_both_paths(graph)

    def test_missing_helper_or_control_and_unexpected_metadata_rejected(self):
        for path in guard.DIAGNOSTIC_PATHS[-2:]:
            graph = copy.deepcopy(self.graph)
            graph['diagnosticDependencySourceBinding']['inputMetadata'].pop(path)
            self.reject_in_both_paths(graph)
        self.graph['diagnosticDependencySourceBinding']['inputMetadata']['Unexpected.cs'] = '100644 blob ' + '0' * 40
        self.reject_in_both_paths(self.graph)

    def test_wrong_blob_digest_change_map_and_producer_rejected(self):
        for location, field, value in [('diagnosticDependencySourceBinding', 'productionBuildInputSha256', '0' * 64),
                                      ('diagnosticDependencySourceBinding', 'reviewedProducer', '0' * 40),
                                      ('intentionalSourceChanges', 'changedInputs', {})]:
            graph = copy.deepcopy(self.graph)
            graph[location][field] = value
            self.reject_in_both_paths(graph)
        path = guard.DIAGNOSTIC_PATHS[-1]
        self.graph['diagnosticDependencySourceBinding']['inputMetadata'][path] = '100644 blob ' + '0' * 40
        self.reject_in_both_paths(self.graph)

    def test_real_git_wrong_head_or_source_ancestry_rejected(self):
        with self.assertRaises(ValueError):
            guard.require_git_admission(self.joined, self.graph, self.source, self.source)
        with self.assertRaises(subprocess.CalledProcessError):
            guard.require_git_admission(self.joined, self.graph, self.head, '0' * 40)
        with self.assertRaises(ValueError):
            guard.require_git_admission(self.joined, self.graph, self.head, self.producer + '0')

    def test_real_git_source_not_ancestor_of_head_rejected(self):
        # A real orphan commit object can be tested without switching owned HEAD.
        tree = self.git(self.owned, 'rev-parse', self.producer + '^{tree}')
        orphan = subprocess.check_output(['git', '-C', str(self.owned), 'commit-tree', tree, '-p', self.producer, '-m', 'Temporary divergent ancestry control'], timeout=15).decode().strip()
        with self.assertRaises(subprocess.CalledProcessError):
            guard.require_git_admission(self.joined, self.graph, self.head, orphan)

    def test_real_git_shallow_history_rejected(self):
        shallow = self.owned / '.git/shallow'
        shallow.write_text(self.producer + '\n', encoding='ascii')
        try:
            with self.assertRaises(ValueError):
                guard.require_git_admission(self.joined, self.graph, self.head, self.source)
        finally:
            shallow.unlink()

    def test_real_git_external_head_drift_rejected(self):
        witness = self.joined / 'Legacy.Maliev.ProcurementService'
        self.git(witness, 'update-ref', 'HEAD', self.source)
        try:
            with self.assertRaises(ValueError):
                guard.require_git_admission(self.joined, self.graph, self.head, self.source)
        finally:
            self.git(witness, 'update-ref', 'HEAD', self.producer)

    def test_real_git_selected_working_bytes_drift_rejected(self):
        path = self.owned / guard.DIAGNOSTIC_PATHS[-1]
        original = path.read_bytes()
        path.write_bytes(original + b'\n// drift\n')
        try:
            with self.assertRaises(ValueError):
                guard.require_git_admission(self.joined, self.graph, self.head, self.source)
        finally:
            path.write_bytes(original)

    def test_historical_predecessor_raw_tamper_rejected(self):
        path = self.owned / guard.OWNER_PREDECESSOR_PATH
        original = path.read_bytes()
        path.write_bytes(original + b'\n')
        try:
            self.reject_in_both_paths(self.graph)
        finally:
            path.write_bytes(original)

    def test_current_and_historical_graph_metadata_cannot_mix(self):
        graph = copy.deepcopy(self.graph)
        graph['references'] = guard.frozen_historical_graph()['references']
        self.reject_in_both_paths(graph)
        graph = guard.frozen_historical_graph()
        graph['diagnosticDependencySourceBinding'] = self.graph['diagnosticDependencySourceBinding']
        self.reject_in_both_paths(graph)

    def test_result_mode_requires_joined_source_and_has_no_downgrade(self):
        with self.assertRaises(ValueError):
            guard.results(self.base, self.graph, owned_head=self.head, source_head=self.source)
        with self.assertRaises(ValueError):
            guard.require_git_admission(self.joined, guard.frozen_historical_graph(), self.head, self.source)

    def test_inactive_types_are_not_waived(self):
        inactive = inactive_source_graph()
        with patch.object(guard, 'DIAGNOSTIC_PRODUCER', None), patch.object(guard, 'FROZEN_DIAGNOSTIC_GRAPH', copy.deepcopy(inactive)):
            for field, value in [('inputCount', 82.0), ('releaseAllowed', 0), ('fixtureInputCount', 16.0)]:
                bad = copy.deepcopy(inactive)
                bad['diagnosticDependencySourceBinding'][field] = value
                with self.assertRaises(ValueError):
                    guard.require_diagnostic_graph(bad, source_only=True)

if __name__ == "__main__":
    unittest.main()
