from pathlib import Path
from collections import Counter
from unittest.mock import patch
import unittest,tempfile,json,uuid,xml.etree.ElementTree as ET,ast
import sys;sys.path.insert(0,str(Path(__file__).resolve().parent))
from types import SimpleNamespace
import procurement_pagination_hosted_guards as g
import procurement_pagination_hosted_driver as driver

TAG='{'+g.NS['t']+'}'
METHOD=g.METHOD
CLASS='Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementPaginationSourceTests'

class P1Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.names=[CLASS+'.'+METHOD+f'(supplier: {i%2==0}, size: null, index: null, search: "match{i}")' for i in range(4)]
        self.roster={'source':'compiled-vstest-discovery','names':self.names[:],'binaryHashes':{'tests.dll':'0'*64},'assemblyPath':'/owned/tests.dll','filter':None}
    def tearDown(self):self.temp.cleanup()
    def evidence(self,red=False):
        root=ET.Element(TAG+'TestRun',id=str(uuid.uuid4()))
        ET.SubElement(root,TAG+'Times',start='2026-10-09T00:00:00Z',finish='2026-10-09T00:01:00Z')
        summary=ET.SubElement(root,TAG+'ResultSummary',outcome='Failed' if red else 'Completed')
        fields=dict(total='4',executed='4',passed='0' if red else '4',failed='4' if red else '0')
        fields.update({key:'0' for key in ('error','timeout','aborted','inconclusive','passedButRunAborted','notRunnable','notExecuted','disconnected','warning','completed','inProgress','pending')})
        ET.SubElement(summary,TAG+'Counters',fields);results=ET.SubElement(root,TAG+'Results');definitions=ET.SubElement(root,TAG+'TestDefinitions');entries=ET.SubElement(root,TAG+'TestEntries')
        for name in self.names:
            tid=str(uuid.uuid4());eid=str(uuid.uuid4())
            row=ET.SubElement(results,TAG+'UnitTestResult',testId=tid,executionId=eid,testName=name,outcome='Failed' if red else 'Passed',startTime='2026-10-09T00:00:01Z',endTime='2026-10-09T00:00:02Z')
            if red:
                info=ET.SubElement(ET.SubElement(row,TAG+'Output'),TAG+'ErrorInfo')
                ET.SubElement(info,TAG+'Message').text='Assert.Equal() Failure: Collections differ';ET.SubElement(info,TAG+'StackTrace').text=METHOD
            definition=ET.SubElement(definitions,TAG+'UnitTest',id=tid,name=name,storage='/owned/tests.dll')
            ET.SubElement(definition,TAG+'Execution',id=eid);ET.SubElement(definition,TAG+'TestMethod',className=CLASS,name=METHOD,codeBase='/owned/tests.dll')
            ET.SubElement(entries,TAG+'TestEntry',testId=tid,executionId=eid)
        self.xml=root;self.write();return root
    def write(self):ET.ElementTree(self.xml).write(self.root/'modeled.trx')
    def refusal(self):
        self.write()
        with self.assertRaises((g.IntegrityError,ValueError)):g.trx(self.root,self.roster)
    def test_complete_joined_green(self):self.evidence();self.assertEqual(g.trx(self.root,self.roster)['passed'],4)
    def test_complete_causal_red(self):self.evidence(True);self.assertEqual(g.trx(self.root,self.roster,True)['failed'],4)
    def test_root_same_ids_without_completion_refused(self):
        self.evidence();self.xml.remove(self.xml.find(TAG+'ResultSummary'));self.refusal()
    def test_repeated_test_identity_refused(self):
        self.evidence();rows=self.xml.find(TAG+'Results');rows[1].set('testId',rows[0].attrib['testId']);self.refusal()
    def test_repeated_execution_identity_refused(self):
        self.evidence();rows=self.xml.find(TAG+'Results');rows[1].set('executionId',rows[0].attrib['executionId']);self.refusal()
    def test_truncated_result_does_not_change_expected_roster(self):
        self.evidence();rows=self.xml.find(TAG+'Results');rows.remove(rows[-1]);self.refusal()
    def test_self_count_argument_refused(self):
        self.evidence()
        with self.assertRaises(g.IntegrityError):g.trx(self.root,4)
    def test_incomplete_summary_refused(self):
        self.evidence();self.xml.find(TAG+'ResultSummary').set('outcome','InProgress');self.refusal()
    def test_counter_mismatch_refused(self):
        self.evidence();self.xml.find(TAG+'ResultSummary').find(TAG+'Counters').set('executed','3');self.refusal()
    def test_definition_name_mismatch_refused(self):
        self.evidence();self.xml.find(TAG+'TestDefinitions')[0].set('name','Foreign.Case');self.refusal()
    def test_unmatched_compiled_display_multiset_refused(self):
        self.evidence();self.roster['names'][0]='Legacy.Maliev.ProcurementService.Tests.Other.Method';self.refusal()
    def test_skipped_result_refused(self):
        self.evidence();self.xml.find(TAG+'Results')[0].set('outcome','NotExecuted');self.refusal()
    def test_toolchain_env_is_consumed_and_preserved(self):
        text='runs:\n  steps:\n    - name: Install Gitleaks\n      env:\n        GOTOOLCHAIN: local\n        GOFLAGS: -trimpath\n      run: go install github.com/zricethezav/gitleaks/v8@'+('a'*40)+'\n'
        spec=g.install_spec(text);env={'GOTOOLCHAIN':'auto'};g.apply_go_spec(env,spec)
        self.assertEqual(env['GOTOOLCHAIN'],'local');self.assertEqual(env['GOFLAGS'],'-trimpath')
    def test_discarded_reviewed_toolchain_refused(self):
        text='runs:\n  steps:\n    - name: Install Gitleaks\n      run: go install github.com/zricethezav/gitleaks/v8@'+('a'*40)+'\n'
        with self.assertRaises(g.IntegrityError):g.install_spec(text)
    def test_autotoolchain_refused(self):
        text='runs:\n  steps:\n    - name: Install Gitleaks\n      env:\n        GOTOOLCHAIN: auto\n      run: go install github.com/zricethezav/gitleaks/v8@'+('a'*40)+'\n'
        with self.assertRaises(g.IntegrityError):g.install_spec(text)
    def test_runner_override_family_removed(self):
        env={'VSTestTestCaseFilter':'needle','XUNIT_MAX_PARALLEL_THREADS':'5','RunSettingsFilePath':'foreign','MTP_TEST_FILTER':'x','DOTNET_TEST_OPTIONS':'x','PATH':'public'}
        removed=g.sanitize_runner_env(env);self.assertEqual(len(removed),5);self.assertEqual(env['PATH'],'public');self.assertNotIn('VSTestTestCaseFilter',env)
    def test_sdk_environment_allows_no_unknown_filter_or_startup_hook(self):
        env=g.runner_environment({'PATH':'public','MALIEV_TEST_RESOURCE_RUN_ID':'owned','UnknownRunnerFilter':'needle','DOTNET_STARTUP_HOOKS':'foreign','TestCaseFilter':'partial','XUNIT_MAX_PARALLEL_THREADS':'9'})
        self.assertEqual(env['MALIEV_TEST_RESOURCE_RUN_ID'],'owned');self.assertEqual(env['PATH'],'public')
        self.assertNotIn('UnknownRunnerFilter',env);self.assertNotIn('DOTNET_STARTUP_HOOKS',env);self.assertNotIn('TestCaseFilter',env)
    def test_callable_container_guard_survives_optimization(self):
        fake=object.__new__(driver.Driver);fake.run='run'
        value={'Id':'id','Config':{'Labels':{'maliev.codex.owner':'commerce-procurement-qualification-20261007','maliev.codex.parent-run':'run','maliev.codex.persistent-data':'false'}},'HostConfig':{'Memory':False,'MemorySwap':1073741824,'NanoCpus':750000000,'Tmpfs':{'/var/lib/postgresql':'rw,size=512m'}},'NetworkSettings':{'Ports':{}},'Mounts':[]}
        fake.docker=lambda *args:json.dumps([value])
        with self.assertRaises(g.IntegrityError):fake.inspect('id')
    def test_no_removable_assert_guards(self):
        for module in (g,driver):self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(ast.parse(Path(module.__file__).read_bytes()))))

    def test_positive_size_baseline_red_is_causal(self):
        self.names=[name.replace('size: null', 'size: 251') for name in self.names]
        self.roster['names']=self.names[:]
        self.evidence(True)
        self.assertEqual(g.trx(self.root,self.roster,True)['failed'],4)

    def test_foreign_positive_size_baseline_red_refused(self):
        self.names=[name.replace('size: null', 'size: 400') for name in self.names]
        self.roster['names']=self.names[:]
        self.evidence(True)
        with self.assertRaises(g.IntegrityError):g.trx(self.root,self.roster,True)

    def test_seventy_case_roster_requires_every_terminal_result(self):
        self.names=[CLASS+'.'+METHOD+f'(supplier: true, size: null, index: null, search: "match{i}")' for i in range(70)]
        self.roster['names']=self.names[:]
        self.evidence()
        counts=self.xml.find(TAG+'ResultSummary').find(TAG+'Counters')
        for key in ('total','executed','passed'):counts.set(key,'70')
        self.write()
        self.assertEqual(g.trx(self.root,self.roster)['actualCases'],70)
        self.xml.find(TAG+'Results').remove(self.xml.find(TAG+'Results')[-1])
        self.refusal()

    def test_full_roster_is_not_trx_self_count(self):
        self.names=[CLASS+'.'+METHOD+f'(supplier: true, size: null, index: null, search: "match{i}")' for i in range(386)]
        self.roster['names']=self.names[:]
        self.evidence()
        counts=self.xml.find(TAG+'ResultSummary').find(TAG+'Counters')
        for key in ('total','executed','passed'):counts.set(key,'386')
        self.write()
        self.assertEqual(g.trx(self.root,self.roster)['actualCases'],386)
        self.roster['names']=self.roster['names'][:-1]
        self.refusal()

    def associated(self, full=False):
        contract=g.roster_contract()
        names=contract['associatedDisplayNames'][:]
        rename=contract['approvedExistingFactRename']
        complete=names+[rename['to'] if row['displayName']==rename['from'] else row['displayName'] for row in contract['originalMainIdentities']]
        return {'source':'compiled-vstest-discovery','names':complete if full else names,
                'allUnfilteredDiscoveredNames':complete,'filter':None if full else 'modeled-associated-selection'}

    def test_complete_associated94_and_unfiltered410_rosters(self):
        self.assertEqual(g.associated_roster(self.associated(),False)['newCases'],94)
        self.assertEqual(g.associated_roster(self.associated(True),True)['fullCases'],410)

    def test_associated_missing_unfiltered_case_refused(self):
        roster=self.associated();roster['allUnfilteredDiscoveredNames']=roster['allUnfilteredDiscoveredNames'][:-1]
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,False)

    def test_associated_class_counts_cannot_swap(self):
        roster=self.associated(True)
        wire=next(name for name in roster['names'] if 'ProcurementPaginationWireContractTests' in name)
        index=roster['names'].index(wire)
        roster['names'][index]=roster['names'][index].replace('ProcurementPaginationWireContractTests.ListPage_PreservesRawEnvelopeFlagsNullOmissionAndEmptyStatus','ProcurementIndependentContactTests.PostAndPutPreserveIndependentContactsThroughFreshReads')
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,True)

    def test_associated_missing_focused_case_refused(self):
        roster=self.associated();roster['names']=roster['names'][:-1]
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,False)

    def test_associated_full_filter_refused(self):
        roster=self.associated(True);roster['filter']='ForeignPartialFilter'
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,True)

    def test_associated_selected_foreign_display_refused(self):
        roster=self.associated();roster['names'][0]='Legacy.Maliev.ProcurementService.Tests.Foreign.Case'
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,False)

    def discovery(self, names, testfilter):
        class ModeledDriver:
            def __init__(self, root):
                self.root=root
                self.receipt={}
            def command(self,label,argv,cwd,timeout):
                if '--list-tests' not in argv: raise AssertionError('Only modeled discovery permitted')
                text='The following Tests are available:\n'+''.join('    '+name+'\n' for name in names)
                (self.root/(label+'.log')).write_text(text,encoding='utf-8')
                return 0,text
            def save(self): pass
        cwd=self.root/'modeled-build'
        folder=cwd/'Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0'
        folder.mkdir(parents=True,exist_ok=True)
        with patch.object(g,'binary_hashes',return_value={'modeled.dll':'0'*64}):
            return g.observe_roster(ModeledDriver(self.root),'actual-filter-path',cwd,testfilter)

    def test_actual_driver_filters_reach_observe_roster(self):
        contract=g.roster_contract()
        baseline=[row['displayName'] for row in contract['originalMainIdentities']]+contract['baselineDisplayNames']
        observed=self.discovery(baseline,driver.BASELINE_FILTER)
        g.baseline_roster(observed)
        self.assertEqual(len(observed['names']),16)
        observed=self.discovery(self.associated(True)['names'],driver.CANDIDATE_FILTER)
        self.assertEqual(g.associated_roster(observed,False)['newCases'],94)

    def test_retired_or_partial_driver_filter_refused(self):
        for testfilter in ['FullyQualifiedName~ProcurementOmittedSizeSourceTests',g.BASELINE_FILTER+'|FullyQualifiedName~ProcurementIndependentContactTests']:
            with self.subTest(testfilter=testfilter):
                with self.assertRaises(g.IntegrityError):self.discovery(self.associated(True)['names'],testfilter)

    def test_repeated_bare_theory_and_duplicate_foreign316_refused(self):
        names=[method for method,count in g.ASSOCIATED_METHOD_COUNTS.items() for _ in range(count)]+['Legacy.Maliev.ProcurementService.Tests.Foreign.Repeated']*316
        roster={'source':'compiled-vstest-discovery','names':names,'allUnfilteredDiscoveredNames':names,'filter':None}
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,True)

    def test_unique_foreign_original_identity_refused(self):
        roster=self.associated(True)
        roster['names'][-1]='Legacy.Maliev.ProcurementService.Tests.Foreign.UniqueReplacement'
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,True)

    def test_unique_wrong_theory_parameter_grammar_refused(self):
        roster=self.associated(True)
        index=next(i for i,name in enumerate(roster['names']) if 'ProcurementPaginationWireContractTests' in name)
        roster['names'][index]=roster['names'][index].replace('page: 0','page: 9000')
        with self.assertRaises(g.IntegrityError):g.associated_roster(roster,True)

    def test_native_focused_and_full_entry_refuse_before_any_command(self):
        for phase in ['focused','full','injections']:
            with self.subTest(phase=phase):
                fake_os=SimpleNamespace(name='posix',environ={'GITHUB_ACTIONS':'true','MALIEV_TEST_RESOURCE_RUN_ID':str(uuid.uuid4())})
                with patch.object(driver,'os',fake_os),patch.object(sys,'argv',['driver','--phase',phase,'--root',str(self.root/phase)]),patch.object(driver.Driver,'command',side_effect=AssertionError('Native command prohibited')) as command:
                    with self.assertRaisesRegex(g.IntegrityError,'Fresh reviewed original allocation byte pin missing'):driver.main()
                    command.assert_not_called()

if __name__=='__main__':unittest.main()
