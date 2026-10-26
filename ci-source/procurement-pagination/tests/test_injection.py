import ast,copy,datetime,hashlib,json,os,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
import procurement_native_injections as n
import procurement_pagination_hosted_driver as d
class Fake:
    run='11111111-1111-4111-8111-111111111111'
    def __init__(self):
        self.receipt={'injectionStartUtc':(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=10)).isoformat(),'postgres':{}}
        self.live={};self.inspections=0
    def save(self):pass
    def owned_containers(self):return list(self.live)
    def docker(self,*args):return '\n'.join(self.live)
    def inspect(self,cid):self.inspections+=1;return self.live[cid]
class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.controls=self.root/'controls';self.controls.mkdir();self.receipts=self.root/'receipts';self.receipts.mkdir();self.driver=Fake();self.cid='a'*64
    def tearDown(self):self.temp.cleanup()
    def event(self,kind='health',**changes):
        row=dict(sequence=1,case='supplier-start',kind=kind,id=self.cid,role='Supplier',fixture='b'*32,testClass=n.CLASSES[0],parentRun=self.driver.run);row.update(changes)
        (self.controls/'0001.json').write_text(json.dumps(row),encoding='utf-8');return row
    def live(self,row):
        self.driver.live[row['id']]=({'Created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'State':{'Running':True}},{'labels':{'maliev.codex.fixture-instance':row['fixture'],'maliev.codex.test-class':row['testClass'],'maliev.codex.database-role':row['role'],'maliev.codex.phase':'candidate'}})
        self.driver.receipt['postgres'][row['id']]={'serverVersionNum':180001}
    def observe(self,case='supplier-start'):n.observe_controls(self.driver,case,self.controls,self.receipts)
    def test_real_observer_health_ack(self):
        row=self.event();self.live(row);self.observe();self.assertEqual(1,self.driver.inspections);self.assertEqual(b'approved',(self.controls/'0001.json.ack').read_bytes())
    def test_unrelated_healthy_pair_refused(self):
        self.event();self.driver.receipt['postgres']['f'*64]={'serverVersionNum':180001}
        with self.assertRaises(KeyError):self.observe()
        self.assertFalse((self.controls/'0001.json.ack').exists())
    def test_crossed_role_refused(self):
        row=self.event();self.live(row);self.driver.live[self.cid][1]['labels']['maliev.codex.database-role']='PurchaseOrder'
        with self.assertRaises(n.IntegrityError):self.observe()
    def test_missing_health_refused(self):
        row=self.event();self.live(row);self.driver.receipt['postgres']={}
        with self.assertRaises(n.IntegrityError):self.observe()
    def test_stale_parent_refused(self):
        self.event(parentRun='foreign')
        with self.assertRaises(n.IntegrityError):self.observe()
    def test_oversize_control_refused(self):
        (self.controls/'0001.json').write_bytes(b'x'*2049)
        with self.assertRaises(n.IntegrityError):self.observe()
    def test_foreign_ack_refused(self):
        row=self.event();self.live(row);(self.controls/'0001.json.ack').write_bytes(b'approved')
        with self.assertRaises(n.IntegrityError):self.observe()
    def test_actual_partial_receipt_rejected_and_acknowledged(self):
        self.event(kind='truncated-read',case='concurrent-append-read',id='',role='',fixture='',testClass='')
        (self.receipts/('b'*32+'.jsonl')).write_bytes(b'{"partial"')
        self.observe('concurrent-append-read');self.assertTrue((self.controls/'0001.json.ack').exists())
    def test_partial_receipt_silent_acceptance_refused(self):
        self.event(kind='truncated-read',case='concurrent-append-read',id='',role='',fixture='',testClass='')
        with self.assertRaises(n.IntegrityError):self.observe('concurrent-append-read')
    def test_no_completion_cannot_qualify(self):
        with self.assertRaises(n.IntegrityError):n.final_controls(self.driver,'constructor-second-role')
    def test_zero_start_constructor_completion_has_no_business_acceptance(self):
        self.event(kind='case-complete',case='constructor-second-role',id='',role='',fixture='',testClass='');self.observe('constructor-second-role')
        self.assertFalse(n.final_controls(self.driver,'constructor-second-role')['nativeBusinessAcceptance'])
    def test_started_id_absence_mandatory(self):
        self.driver.receipt['injectionEvents']={'1':{'row':{'kind':'case-complete','sequence':1}}};self.driver.receipt['injectionStartedIds']={self.cid:{'role':'Supplier'}}
        with self.assertRaises(n.IntegrityError):n.final_controls(self.driver,'order-start-after-supplier')
    def test_terminal_sequence_gap_refused(self):
        self.driver.receipt['injectionEvents']={'2':{'row':{'kind':'case-complete','sequence':2}}}
        with self.assertRaises(n.IntegrityError):n.final_controls(self.driver,'constructor-second-role')
    def test_actual_injections_entry_still_blocks_before_any_command(self):
        from types import SimpleNamespace
        with patch.object(d,'os',SimpleNamespace(name='posix',environ=os.environ)),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','MALIEV_TEST_RESOURCE_RUN_ID':self.driver.run}),patch.object(sys,'argv',['driver','--phase','injections','--root',str(self.root/'blocked')]),patch.object(d.Driver,'command',side_effect=AssertionError('Native command is prohibited')):
            with self.assertRaises(n.IntegrityError):d.main()
    def test_nine_actual_xunit_facts_and_case_map(self):
        text=(R/'injection-postimages/ProcurementFiniteFailureInjectionTests.cs').read_text(encoding='utf-8')
        facts=re.findall(r'\[Fact\]\s*public\s+(?:async\s+)?Task\s+(\w+)\(',text)
        self.assertEqual(set(n.CASE_METHODS.values()),set(facts));self.assertEqual(9,len(facts))
        for term in ('Record.ExceptionAsync','First(failure)','Contains<TimeoutException>','BothDisposed()','StartedIds.Count','CompleteAsync()'):self.assertIn(term,text)
    def test_actual_stream_failure_and_finite_delayed_disposal_source(self):
        text=(R/'injection-postimages/ProcurementQualificationFaults.cs').read_text(encoding='utf-8')
        for term in ('if (fail) stream.Dispose()','stream.Write(bytes)','TimeSpan.FromSeconds(31)','WaitForCleanupAsync(pending)','PendingDisposals.Add(pending)','TimeSpan.FromSeconds(60)','eventSequence > 64','bytes.Length > 2048','TimeSpan.FromSeconds(20)','StartedContainers.TryGetValue'):self.assertIn(term,text)
    def test_hard_gate_precedes_injection_branch(self):
        t=(R/'procurement_pagination_hosted_driver.py').read_text(encoding='utf-8')
        self.assertLess(t.index('    binding = admit('),t.index("    if args.phase == 'injections':"))
        self.assertLess(t.index("    require_class_attribution_qualification(execution_admitted=binding['qualificationExecutionAllowed'])"),t.index("    if args.phase == 'injections':"))
        for term in ("suite.get('actualCases') == 410","suite.get('passed') == 410","go version go1.26.9","run_injections(driver, root / 'candidate')"):self.assertIn(term,t)
    def test_qualified_copy_discovery_is410_plus9(self):
        t=(R/'procurement_native_injections.py').read_text(encoding='utf-8')
        self.assertIn("len(complete['names'])==419",t);self.assertIn('associated_roster(business,full=True)',t);self.assertIn("proof['actualCases']==1 and proof['passed']==1",t)
    def test_exact_instrumentation_fixture_cleanup_source(self):
        t=(R/'injection-postimages/ProcurementRuntimeParityTests.cs').read_text(encoding='utf-8')
        for term in ('DisposeConstructedAsync(acquired)','StartedAsync(supplier,','StartedAsync(order,','ThrowAt("supplier-start")','ThrowAt("order-start-after-supplier")','ThrowAt("constructor-second-role")','DisposeRoleAsync(container, role)'):self.assertIn(term,t)
    def test_runner_preserves_only_added_control_env(self):
        env=d.runner_environment({'MALIEV_QUALIFICATION_CASE':'supplier-start','MALIEV_QUALIFICATION_CONTROLS':'/owned/control','FOREIGN_KEY':'x'})
        self.assertEqual('supplier-start',env['MALIEV_QUALIFICATION_CASE']);self.assertNotIn('FOREIGN_KEY',env)
    def test_actual_installer_keeps_candidate_unchanged(self):
        candidate=self.root/'candidate';tests=candidate/'Legacy.Maliev.ProcurementService.Tests/Integration';tests.mkdir(parents=True)
        original=R/'attribution-postimages'
        for name in ('ProcurementRuntimeParityTests.cs','ProcurementFixtureReceipt.cs'):(tests/name).write_bytes((original/name).read_bytes())
        before={f.name:f.read_bytes() for f in tests.iterdir()};target=self.root/'qualification'
        n.install_copy(candidate,target)
        self.assertEqual(before,{f.name:f.read_bytes() for f in tests.iterdir()})
        for f in (R/'injection-postimages').glob('*.cs'):self.assertEqual(f.read_bytes(),(target/'Legacy.Maliev.ProcurementService.Tests/Integration'/f.name).read_bytes())
if __name__=='__main__':unittest.main()
