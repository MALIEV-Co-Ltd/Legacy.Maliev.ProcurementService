from pathlib import Path
from collections import Counter
from unittest.mock import patch
import unittest,tempfile,json,uuid,xml.etree.ElementTree as ET,ast
import sys;sys.path.insert(0,str(Path(__file__).resolve().parent))
import procurement_pagination_hosted_guards as g
import procurement_pagination_hosted_driver as driver

TAG='{'+g.NS['t']+'}'
METHOD=g.METHOD
CLASS='Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementOmittedSizeSourceTests'

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

if __name__=='__main__':unittest.main()
