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
        original_checkout = baseline if baseline.exists() else SOURCE_REPO
        self.original = guard.git(original_checkout, "show", guard.BASE + ":" + guard.FIXTURE)
        # A shallow candidate checkout contains HEAD; exact fixture SHA remains checked by the guard.
        self.reviewed = guard.git(SOURCE_REPO, "show", "HEAD:" + guard.FIXTURE)

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
        harness = guard.git(SOURCE_REPO, "show", "HEAD:" + guard.TEST)
        guard.require_harness_binding(harness)
        with self.assertRaises(ValueError):
            guard.require_harness_binding(harness + b"drift")


    def test_committed_lf_overlay_passes_and_packet_crlf_is_rejected(self):
        import json
        root = pathlib.Path(__file__).resolve().parents[1]
        overlay = json.loads((root / "docs/procurement-supplier-address-fixture-startup-overlay.json").read_text(encoding="utf-8"))
        committed = guard.git(SOURCE_REPO, "show", "HEAD:docs/procurement-supplier-address-fixture-overlay.json")
        self.assertNotIn(b"\r\n", committed)
        guard.require_previous_overlay(overlay, committed)
        with self.assertRaises(ValueError):
            guard.require_previous_overlay(overlay, committed.replace(b"\n", b"\r\n"))

    def test_helper_exact_phase_and_drift_custody(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        helper = guard.git(SOURCE_REPO, "show", "HEAD:" + guard.HELPER)
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
        raw = guard.git(SOURCE_REPO, "show", "HEAD:docs/procurement-supplier-address-fixture-startup-overlay.json")
        guard.require_previous_startup_overlay(overlay, raw)
        with self.assertRaises(ValueError):
            guard.require_previous_startup_overlay(overlay, raw.replace(b"\n", b"\r\n"))
        for field in overlay["previousReviewedStartupOverlay"]:
            mutated = copy.deepcopy(overlay)
            mutated["previousReviewedStartupOverlay"][field] = "drift"
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.require_previous_startup_overlay(mutated, raw)



# Source-only controls use immutable Git bytes and temporary simulated baseline scopes.
from pathlib import Path
import copy, hashlib, json, os, subprocess
from unittest.mock import patch
SOURCE_REPO=Path(os.environ.get("OWNER_GUARD_SOURCE_REPO", str(Path(__file__).resolve().parents[1])))
def baseline_repository():
    separate=SOURCE_REPO/".address-baseline"
    return separate if separate.exists() else SOURCE_REPO
def baseline_bytes(path):
    return subprocess.check_output(["git", "-C", str(baseline_repository()), "show", guard.BASE+":"+path], timeout=15)
def source_bytes(path, ref="HEAD"):
    return subprocess.check_output(["git", "-C", str(SOURCE_REPO), "show", ref+":"+path], timeout=15)
class CausalOwnerControls(unittest.TestCase):
 def setUp(self):
  self.fixture=source_bytes(guard.FIXTURE);self.helper=source_bytes(guard.OWNER_HELPER)
  self.original_fixture=baseline_bytes(guard.FIXTURE)
  self.previous=source_bytes(guard.PREVIOUS_JOURNAL_OVERLAY)
  self.overlay=json.loads((Path(__file__).resolve().parents[1]/'docs/procurement-supplier-address-fixture-owner-correlation-overlay.json').read_text(encoding='utf-8'))
 def test_unbound_producer_refuses_prepare_before_any_baseline_mutation(self):
  with patch.object(guard,'FIXTURE_PRODUCER',None):
   with self.assertRaises(ValueError):guard.prepare(Path('unit-only-nonexistent-baseline'),Path('unit-only-missing-manifest'))
 def test_owner_helper_positive_before_and_after_exact_bytes(self):
  guard.require_owner_helper_binding(self.helper,None,False);guard.require_owner_helper_binding(self.helper,self.helper,True)
 def test_owner_helper_preexisting_before_overlay_rejected(self):
  with self.assertRaises(ValueError):guard.require_owner_helper_binding(self.helper,self.helper,False)
 def test_owner_helper_drift_rejected(self):
  with self.assertRaises(ValueError):guard.require_owner_helper_binding(self.helper+b'changed',None,False)
 def test_owner_helper_missing_or_changed_after_execution_rejected(self):
  for value in [None,self.helper+b'changed']:
   with self.assertRaises(ValueError):guard.require_owner_helper_binding(self.helper,value,True)
 def test_fixture_original95_and_identical_overlay_positive(self):
  guard.require_fixture_binding(self.fixture,self.original_fixture,self.original_fixture,False)
  guard.require_fixture_binding(self.fixture,self.fixture,self.original_fixture,True)
 def test_fixture_or_original95_drift_rejected(self):
  with self.assertRaises(ValueError):guard.require_fixture_binding(self.fixture+b'changed',self.original_fixture,self.original_fixture,False)
  with self.assertRaises(ValueError):guard.require_fixture_binding(self.fixture,self.original_fixture,self.original_fixture+b'changed',False)
 def test_original_before_cannot_be_substituted_for_reviewed_after(self):
  with self.assertRaises(ValueError):guard.require_fixture_binding(self.fixture,self.original_fixture,self.original_fixture,True)
 def test_previous_journal_overlay_positive(self):
  guard.require_previous_journal_overlay(self.overlay,self.previous)
 def test_previous_journal_overlay_drift_rejected(self):
  with self.assertRaises(ValueError):guard.require_previous_journal_overlay(self.overlay,self.previous+b'changed')
 def test_previous_journal_metadata_drift_rejected(self):
  self.overlay['previousReviewedJournalOverlay']['producer']='b'*40
  with self.assertRaises(ValueError):guard.require_previous_journal_overlay(self.overlay,self.previous)
 def test_frozen33_harness_positive_and_drift_rejection(self):
  harness=source_bytes(guard.TEST)
  guard.require_harness_binding(harness)
  with self.assertRaises(ValueError):guard.require_harness_binding(harness+b'changed')
 def test_release_accepts_only_canonical_pin_format_source_control(self):
  old=guard.FIXTURE_PRODUCER
  try:
   for value in [None,'main','A'*40]:
    guard.FIXTURE_PRODUCER=value
    with self.assertRaises(ValueError):guard.require_release_producer()
   guard.FIXTURE_PRODUCER='a'*40;guard.require_release_producer()
  finally:guard.FIXTURE_PRODUCER=old

class CausalPhaseScopeControls(unittest.TestCase):
 def setUp(self):
  import tempfile,subprocess
  self.temporary=tempfile.TemporaryDirectory(prefix='owner-overlay-source-control-')
  self.addCleanup(self.temporary.cleanup)
  self.root=Path(self.temporary.name);self.candidate=self.root/'candidate';self.baseline=self.root/'baseline'
  self.baseline.mkdir();self.candidate.mkdir();self.producer='a'*40
  self.producer_repo=self.candidate/'.dependencies/ProcurementFixtureProducer';self.producer_repo.mkdir(parents=True)
  self.old_file=guard.__file__;self.old_producer=guard.FIXTURE_PRODUCER
  guard.__file__=str(self.candidate/'scripts/prepare.py');guard.FIXTURE_PRODUCER=self.producer
  self.addCleanup(setattr,guard,'__file__',self.old_file);self.addCleanup(setattr,guard,'FIXTURE_PRODUCER',self.old_producer)
  self.repo=str(SOURCE_REPO)
  self.original_fixture=baseline_bytes(guard.FIXTURE)
  self.original_model=baseline_bytes(guard.MODEL)
  self.harness=subprocess.check_output(['git','-C',self.repo,'show','HEAD:'+guard.TEST],timeout=15)
  for rel,raw in [(guard.FIXTURE,source_bytes(guard.FIXTURE)),(guard.OWNER_HELPER,source_bytes(guard.OWNER_HELPER)),(guard.HELPER,subprocess.check_output(['git','-C',self.repo,'show','HEAD:'+guard.HELPER],timeout=15)),(guard.TEST,self.harness)]:
   f=self.candidate/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
  for relative in ['docs/procurement-supplier-address-fixture-overlay.json','docs/procurement-supplier-address-fixture-startup-overlay.json',guard.PREVIOUS_JOURNAL_OVERLAY,'docs/procurement-supplier-address-fixture-owner-correlation-overlay.json']:
   dst=self.candidate/relative;dst.parent.mkdir(parents=True,exist_ok=True)
   raw=(Path(__file__).resolve().parents[1]/relative).read_bytes() if 'owner-correlation' in relative else source_bytes(relative)
   dst.write_bytes(raw)
  overlaypath=self.candidate/'docs/procurement-supplier-address-fixture-owner-correlation-overlay.json'
  overlay=json.loads(overlaypath.read_text(encoding='utf-8'));overlay['reviewedFixtureProducer']=self.producer;overlay['ownerCorrelationHelper']['producer']=self.producer;overlay['releaseAllowed']=True
  overlaypath.write_bytes((json.dumps(overlay)+'\n').encode())
  for rel,raw in [(guard.FIXTURE,self.original_fixture),(guard.MODEL,self.original_model)]:
   f=self.baseline/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
  self.manifest=self.candidate/'cases.json';self.manifest.write_bytes(json.dumps({'expectedCases':33,'cases':[None]*33}).encode())
  self.extra_tracked=set();self.patch=patch.object(guard,'git',side_effect=self.fake_git);self.patch.start();self.addCleanup(self.patch.stop)
 def fake_git(self,root,*args):
  root=Path(root)
  if args==('rev-parse','HEAD'):return (guard.BASE if root==self.baseline else self.producer).encode()+b'\n'
  if args==('rev-parse','--is-shallow-repository'):return b'true\n'
  if args[0]=='rev-parse' and ':' in args[1]:
   path=args[1].split(':',1)[1];return ((guard.FIXTURE_BLOB if path==guard.FIXTURE else guard.OWNER_HELPER_BLOB)+'\n').encode()
  if args==('rev-parse','HEAD^{tree}'):return b'unit-only-simulated-tree\n'
  if args==('diff','--cached','--name-only'):return b''
  if args==('diff','--name-only'):
   if root==self.producer_repo:return b''
   paths=set(self.extra_tracked)
   if (self.baseline/guard.FIXTURE).read_bytes()!=self.original_fixture:paths.add(guard.FIXTURE)
   if (self.baseline/guard.MODEL).read_bytes()!=self.original_model:paths.add(guard.MODEL)
   return ('\n'.join(sorted(paths))).encode()
  if args[0]=='show':
   ref,path=args[1].split(':',1)
   if root==self.producer_repo and ref==self.producer:return (self.candidate/path).read_bytes()
   if root==self.baseline and ref==guard.BASE:
    if path==guard.FIXTURE:return self.original_fixture
    if path==guard.MODEL:return self.original_model
   raise AssertionError('Unexpected simulated show')
  if args[:2]==('ls-tree',guard.BASE):return b''
  if args==('ls-files','--others','--exclude-standard'):
   if root==self.producer_repo:return b''
   tracked={guard.FIXTURE,guard.MODEL}|self.extra_tracked
   return ('\n'.join(sorted(f.relative_to(self.baseline).as_posix() for f in self.baseline.rglob('*') if f.is_file() and f.relative_to(self.baseline).as_posix() not in tracked))).encode()
  raise AssertionError('Unexpected simulated Git command: '+repr(args))
 def test_complete_simulated_before_after_overlay_exact_scope(self):
  guard.prepare(self.baseline,self.manifest)
  guard.prepare(self.baseline,self.manifest,True)
  proof=json.loads((self.candidate/'address-causal-results/source-binding-after.json').read_text(encoding='utf-8'))
  self.assertFalse(proof['baselineNativeExecutionProven'])
  self.assertEqual(guard.OWNER_HELPER,proof['ownerCorrelationHelper'])
 def test_unexpected_tracked_path_rejected_before_overlay(self):
  self.extra_tracked.add('unreviewed-tracked.cs')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)
 def test_unexpected_untracked_before_overlay_refuses_without_modification(self):
  (self.baseline/'unexpected.txt').write_bytes(b'unit-only')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)
  self.assertEqual(self.original_fixture,(self.baseline/guard.FIXTURE).read_bytes())
  self.assertFalse((self.baseline/guard.OWNER_HELPER).exists())
 def test_unexpected_untracked_file_rejected_after_overlay(self):
  guard.prepare(self.baseline,self.manifest);(self.baseline/'unexpected.txt').write_bytes(b'unit-only')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest,True)
 def test_owner_helper_changed_after_overlay_rejected(self):
  guard.prepare(self.baseline,self.manifest)
  f=self.baseline/guard.OWNER_HELPER;f.write_bytes(f.read_bytes()+b'changed')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest,True)
 def test_production_model_change_rejected(self):
  f=self.baseline/guard.MODEL;f.write_bytes(f.read_bytes()+b'changed')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)
 def test_new_converter_leak_rejected(self):
  f=self.baseline/guard.CONVERTER;f.write_bytes(b'unit-only-new-converter')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)
 def test_original_journal_drift_rejected(self):
  f=self.candidate/guard.HELPER;f.write_bytes(f.read_bytes()+b'changed')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)
 def test_frozen_harness_drift_rejected(self):
  f=self.candidate/guard.TEST;f.write_bytes(f.read_bytes()+b'changed')
  with self.assertRaises(ValueError):guard.prepare(self.baseline,self.manifest)


class RealShallowLayoutControls(unittest.TestCase):
    def test_separate_real_shallow_baseline_and_producer_before_after_and_refusals(self):
        import tempfile
        # Real Git object custody, source-only: no Docker, .NET, or native test phase.
        with tempfile.TemporaryDirectory(prefix="owner-real-shallow-") as temporary:
            root = Path(temporary)
            seed, candidate = root / "seed", root / "candidate"

            def command(repository, *args):
                return subprocess.check_output(["git", "-C", str(repository), *args],
                                               stderr=subprocess.STDOUT, timeout=30)

            def shallow_checkout(source, revision, target):
                target.mkdir(parents=True)
                command(target, "init", "--quiet")
                command(target, "fetch", "--quiet", "--depth=1", "--no-tags",
                        "--no-recurse-submodules", str(source), revision)
                command(target, "checkout", "--quiet", "--detach", "FETCH_HEAD")
                self.assertEqual(b"true", command(target, "rev-parse", "--is-shallow-repository").strip())

            head = command(SOURCE_REPO, "rev-parse", "HEAD").decode().strip()
            shallow_checkout(SOURCE_REPO, head, seed)
            active = Path(__file__).resolve().parents[1]
            # Rehearse the current proposed guard/overlay bytes before their publication.
            for relative in ["scripts/prepare-supplier-address-causal-baseline.py",
                             "docs/procurement-supplier-address-fixture-owner-correlation-overlay.json",
                             "scripts/test_supplier_address_fixture_overlay.py"]:
                (seed / relative).write_bytes((active / relative).read_bytes())
            (seed / "unit-only-shallow-candidate.txt").write_bytes(b"Source-only candidate; no native proof\n")
            command(seed, "add", "scripts/prepare-supplier-address-causal-baseline.py",
                    "docs/procurement-supplier-address-fixture-owner-correlation-overlay.json",
                    "scripts/test_supplier_address_fixture_overlay.py",
                    "unit-only-shallow-candidate.txt")
            command(seed, "-c", "user.name=Source control", "-c", "user.email=source-control@example.invalid",
                    "-c", "core.hooksPath=" + str(root / "no-hooks"), "commit", "--quiet", "-m", "Temporary shallow source control")
            candidate_head = command(seed, "rev-parse", "HEAD").decode().strip()
            shallow_checkout(seed, candidate_head, candidate)
            for absent in [guard.BASE, guard.FIXTURE_PRODUCER]:
                with self.assertRaises(subprocess.CalledProcessError):
                    command(candidate, "cat-file", "-e", absent + "^{commit}")
            baseline = candidate / ".address-baseline"
            shallow_checkout(baseline_repository(), guard.BASE, baseline)
            producer = candidate / ".dependencies/ProcurementFixtureProducer"
            producer_source = SOURCE_REPO / ".dependencies/ProcurementFixtureProducer"
            if not producer_source.exists():
                producer_source = SOURCE_REPO
            shallow_checkout(producer_source, guard.FIXTURE_PRODUCER, producer)
            # Execute all 31 existing/owner controls from the real hosted-style layout.
            # Exclude this layout constructor to avoid recursive test runs.
            import sys
            environment = dict(os.environ, OWNER_GUARD_SOURCE_REPO=str(candidate))
            control_args = [sys.executable, "-B"] + (["-O"] if sys.flags.optimize else [])
            control_args += ["-m", "unittest",
                             "test_supplier_address_fixture_overlay.FixtureOverlayControls",
                             "test_supplier_address_fixture_overlay.CausalOwnerControls",
                             "test_supplier_address_fixture_overlay.CausalPhaseScopeControls"]
            control = subprocess.run(control_args, cwd=candidate / "scripts", env=environment,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
            self.assertEqual(0, control.returncode, control.stdout.decode("utf-8", errors="replace"))
            self.assertIn(b"Ran 31 tests", control.stdout)
            manifest = active / "docs/procurement-supplier-address-causal-contract.json"
            if not manifest.exists():
                manifest = SOURCE_REPO / "docs/procurement-supplier-address-causal-contract.json"
            with patch.object(guard, "__file__", str(candidate / "scripts/prepare-supplier-address-causal-baseline.py")):
                # Missing or wrong witness fails before the baseline overlay is written.
                hidden = producer.with_name("hidden-unit-producer")
                producer.rename(hidden)
                with self.assertRaises(subprocess.CalledProcessError):
                    guard.prepare(baseline, manifest)
                self.assertFalse((baseline / guard.OWNER_HELPER).exists())
                producer.mkdir()
                shallow_checkout(seed, candidate_head, producer / "wrong")
                # A real candidate HEAD as witness is rejected; no mocked Git responses.
                wrong = producer / "wrong"
                wrong.rename(root / "wrong-producer")
                producer.rmdir()
                (root / "wrong-producer").rename(producer)
                with self.assertRaises(ValueError):
                    guard.prepare(baseline, manifest)
                self.assertFalse((baseline / guard.OWNER_HELPER).exists())
                producer.rename(root / "rejected-producer")
                hidden.rename(producer)
                guard.prepare(baseline, manifest)
                guard.prepare(baseline, manifest, True)
            proof = json.loads((candidate / "address-causal-results/source-binding-after.json").read_text(encoding="utf-8"))
            self.assertEqual(candidate_head, proof["candidateCommit"])
            self.assertEqual(guard.FIXTURE_PRODUCER, proof["producerCheckoutHead"])
            self.assertTrue(proof["producerCheckoutShallow"])
            self.assertFalse(proof["baselineNativeExecutionProven"])
            self.assertEqual({guard.FIXTURE}, set(command(baseline, "diff", "--name-only").decode().splitlines()))
            self.assertEqual({guard.TEST, guard.HELPER, guard.OWNER_HELPER},
                             set(command(baseline, "ls-files", "--others", "--exclude-standard").decode().splitlines()))

if __name__ == "__main__":
    unittest.main()
