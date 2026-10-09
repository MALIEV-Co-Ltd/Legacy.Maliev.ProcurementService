import hashlib,json,sys,tempfile,unittest,yaml
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'ci-source/procurement-pagination'))
import procurement_hosted_binding as b
import procurement_pagination_hosted_guards as g
import procurement_pagination_hosted_driver as d
class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'allocation.json';self.now=datetime(2026,10,10,tzinfo=timezone.utc)
        self.a=dict(owner=d.OWNER,allocationId='7a5374ad-1a8b-4dad-8b9f-349d304b1d94',repository=b.REPOSITORY,workflow=b.WORKFLOW,transportCommit='a'*40,job='validate',issuedUtc=self.now.isoformat(),expiresUtc=(self.now+timedelta(seconds=3600)).isoformat(),floorKiB=4194304,jobTimeoutMinutes=60,v3SealSha256=b.V3_SEAL,v3ManifestSha256=b.V3_MANIFEST,purpose='original-procurement-qualification')
        self.env=dict(GITHUB_ACTIONS='true',RUNNER_OS='Linux',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY=b.REPOSITORY,GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF=b.REPOSITORY+'/'+b.WORKFLOW+'@refs/heads/reviewed',GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_JOB='validate',MALIEV_TEST_RESOURCE_RUN_ID=self.a['allocationId'])
    def tearDown(self):self.temp.cleanup()
    def call(self,memory=4194304,pin=True):
        raw=json.dumps(self.a).encode();self.path.write_bytes(raw)
        return b.admit(self.path,hashlib.sha256(raw).hexdigest() if pin else None,self.env,self.now,memory)
    def test_model_admission_is_not_native_acceptance(self):
        row=self.call();self.assertTrue(row['qualificationExecutionAllowed']);self.assertFalse(row['nativeAccepted']);self.assertEqual('123',row['runId'])
    def test_no_byte_pin_refuses(self):
        with self.assertRaises(g.IntegrityError):self.call(pin=False)
    def test_wrong_byte_pin_refuses(self):
        self.call()
        with self.assertRaises(g.IntegrityError):b.admit(self.path,'b'*64,self.env,self.now,4194304)
    def test_expired_refuses(self):
        self.a['expiresUtc']=self.now.isoformat()
        with self.assertRaises(g.IntegrityError):self.call()
    def test_future_refuses(self):
        self.a['issuedUtc']=(self.now+timedelta(seconds=1)).isoformat()
        with self.assertRaises(g.IntegrityError):self.call()
    def test_widened_refuses(self):
        self.a['expiresUtc']=(self.now+timedelta(seconds=3601)).isoformat()
        with self.assertRaises(g.IntegrityError):self.call()
    def test_floor_refuses(self):
        with self.assertRaises(g.IntegrityError):self.call(memory=4194303)
    def test_changed_caps_refuse(self):
        for key,value in [('floorKiB',4194303),('jobTimeoutMinutes',61),('floorKiB',True)]:
            with self.subTest(key=key,value=value):
                old=self.a[key];self.a[key]=value
                with self.assertRaises(g.IntegrityError):self.call()
                self.a[key]=old
    def test_wrong_host_tuple_refuses(self):
        for key,value in [('RUNNER_OS','Windows'),('GITHUB_SHA','b'*40),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_REPOSITORY','foreign'),('GITHUB_JOB','foreign'),('GITHUB_EVENT_NAME','push'),('GITHUB_RUN_ID','0'),('MALIEV_TEST_RESOURCE_RUN_ID','foreign')]:
            with self.subTest(key=key):
                old=self.env[key];self.env[key]=value
                with self.assertRaises(g.IntegrityError):self.call()
                self.env[key]=old
    def test_retry_refuses_spent_allocation(self):
        self.env['GITHUB_RUN_ATTEMPT']='2'
        with self.assertRaises(g.IntegrityError):self.call()
    def test_wrong_parent_source_pins_refuse(self):
        for key in ('v3SealSha256','v3ManifestSha256'):
            with self.subTest(key=key):
                old=self.a[key];self.a[key]='b'*64
                with self.assertRaises(g.IntegrityError):self.call()
                self.a[key]=old
    def test_extra_key_refuses(self):
        self.a['override']=True
        with self.assertRaises(g.IntegrityError):self.call()
    def test_missing_field_refuses(self):
        del self.a['job']
        with self.assertRaises(g.IntegrityError):self.call()
    def test_default_attribution_guard_stays_closed(self):
        with self.assertRaises(g.IntegrityError):g.require_class_attribution_qualification()
        self.assertFalse(g.CLASS_RESOURCE_ATTRIBUTION_QUALIFIED)
    def test_qualification_entry_does_not_flip_acceptance_flag(self):
        g.require_class_attribution_qualification(execution_admitted=True)
        self.assertFalse(g.CLASS_RESOURCE_ATTRIBUTION_QUALIFIED)
        with self.assertRaises(g.IntegrityError):g.require_class_attribution_qualification(execution_admitted='true')
    def test_insufficient_remaining_allocation_blocks_before_popen(self):
        driver=d.Driver(Path(self.temp.name),'model');driver.receipt['hostedExecutionBinding']={'expiresUtc':'2000-01-01T00:00:00+00:00'}
        with patch.object(d.subprocess,'Popen') as process:
            with self.assertRaises(g.IntegrityError):driver.command('not-started',['git','status'],Path(self.temp.name),10)
            process.assert_not_called()
    def test_caller_admits_before_sdk_and_remains_unactivated(self):
        text=(R/b.WORKFLOW).read_text()
        self.assertLess(text.index('Admit exact original hosted allocation'),text.index('Set up reviewed SDK'))
        self.assertIn('if: ${{ false }}',text);self.assertIn('timeout-minutes: 60',text)
    def test_runner_context_is_initialized_in_step_not_job_env(self):
        caller=yaml.safe_load((R/b.WORKFLOW).read_bytes());job=caller['jobs']['validate']
        self.assertNotIn('VALIDATION_ROOT',job['env']);self.assertNotIn('MALIEV_PROCUREMENT_ALLOCATION_FILE',job['env'])
        self.assertTrue(all('runner.' not in str(value) for value in job['env'].values()))
        setup=job['steps'][0]['run']
        self.assertIn("os.environ['RUNNER_TEMP']",setup);self.assertIn('MALIEV_PROCUREMENT_ALLOCATION_FILE=',setup)
if __name__=='__main__':unittest.main()
