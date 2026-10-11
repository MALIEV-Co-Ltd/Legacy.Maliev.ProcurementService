import copy
import importlib.util
import json
import pathlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import supplier_address_owned_processes as processes

spec=importlib.util.spec_from_file_location('observer',pathlib.Path(__file__).with_name('observe-supplier-address-providers.py'))
observer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ProviderObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.output=self.root/'results'
        self.container_ids=['a'*64,'b'*64];self.ps_count=0;self.volume_count=0
        self.remaining=False;self.volume_remaining=False;self.session_mismatch=False
        self.missing_log=False;self.missing_event=False;self.preexisting=False
        self.timeout=False;self.cleanup_failure=False;self.wait_failure=False;self.inspect_failure=False;self.inspect_count=0;self.custody_failure=False;self.killed=False
        self.initial_docker_failure=False;self.initial_volume_failure=False
        self.metadata={key:{'Id':key,'Created':'2026-10-11T01:00:01Z','Image':'sha256:fixture',
            'Config':{'Image':'postgres:18.1-bookworm','Labels':{'org.testcontainers.session-id':'session'},'Env':['NEVER_PRINT=secret-canary']},
            'State':{'StartedAt':'2026-10-11T01:00:02Z'},'NetworkSettings':{'Ports':{'5432/tcp':[{'HostIp':'0.0.0.0','HostPort':'49100'}]}},
            'Mounts':[{'Type':'volume','Name':'owned-'+key[0],'Destination':'/var/lib/postgresql'}]} for key in self.container_ids}

    def docker(self,*args,**kwargs):
        if args[0]=='ps':
            self.ps_count+=1
            if self.initial_docker_failure and self.ps_count==1:raise OSError('synthetic initial Docker failure')
            return '\n'.join(self.container_ids) if self.ps_count==2 or self.remaining and self.ps_count>2 else ''
        if args[0]=='volume':
            self.volume_count+=1
            if self.initial_volume_failure and self.volume_count==1:raise OSError('synthetic initial volume failure')
            return 'owned-a' if self.preexisting and self.volume_count==1 or self.volume_remaining and self.volume_count>1 else ''
        if args[0]=='inspect':
            self.inspect_count+=1
            if self.inspect_failure and self.inspect_count==2:raise OSError('synthetic second inspect failure')
            metadata=copy.deepcopy(self.metadata[args[1]])
            if self.session_mismatch and args[1]==self.container_ids[1]:metadata['Config']['Labels']['org.testcontainers.session-id']='other'
            return json.dumps([metadata])
        if args[0]=='events':
            return '\n'.join(json.dumps({'Type':'container','Actor':{'ID':key},'Action':action,'timeNano':index}) for key in self.container_ids for index,action in enumerate(('start','die','destroy')) if not self.missing_event or action!='destroy')
        raise AssertionError(args)

    def popen(self,*args,**kwargs):
        self.assertEqual('FullyQualifiedName~ProcurementSupplierAddressScalarStringTests', args[0][args[0].index('--filter')+1])
        self.assertIn('--no-build', args[0])
        self.assertIn('--no-restore', args[0])
        self.assertIn('--disable-build-servers', args[0])
        for key in self.container_ids:
            for phrase in ('Docker container '+key[:12]+' created','Start Docker container '+key[:12],'Delete Docker container '+key[:12]):
                if not self.missing_log or not phrase.startswith('Delete'):kwargs['stdout'].write(phrase+'\n')
        (self.output/'results.trx').write_text('<TestRun><ResultSummary><Output><StdOut /></Output></ResultSummary></TestRun>')
        test=self
        class Process:
            pid=123
            polls=0
            def poll(self):
                if test.wait_failure:return 0 if test.killed else None
                self.polls+=1
                return None if self.polls==1 else 0
            def wait(self,timeout):
                if test.wait_failure and not test.killed:raise subprocess.TimeoutExpired('synthetic',timeout)
                return 0
            def terminate(self):raise OSError('synthetic terminate failure')
            def kill(self):test.killed=True
        return Process()

    def run_observer(self):
        test=self
        class Session:
            def __init__(self,process):
                if test.custody_failure:raise OSError('synthetic custody failure')
            def capture(self):
                if test.timeout:raise ValueError('Filtered test process timed out')
            def cleanup(self,failed=False):
                if test.cleanup_failure:raise OSError('synthetic cleanup failure')
                return {'verified':True,'forcedCleanup':False,'handlesClosed':True,'members':[]}
        with patch.object(observer,'docker',self.docker),patch.object(observer.subprocess,'Popen',self.popen),patch.object(observer,'process_identity',return_value={'processId':123,'actualStartTimeUtc':'synthetic','executable':'synthetic'}),patch.object(observer,'OwnedSession',Session),patch.object(observer.time,'sleep'):
            return observer.observe(self.root,self.output,'candidate')

    def test_positive_and_no_environment_capture(self):
        self.assertEqual(0,self.run_observer())
        raw=(self.output/'provider-observation.json').read_text()
        self.assertNotIn('secret-canary',raw)
        self.assertTrue(json.loads(raw)['normalFixtureDisposalProven'])

    def assert_refused_receipt(self, cause, resources=2):
        receipt=json.loads((self.output/'provider-observation.json').read_text())
        self.assertIn(cause,receipt['primaryFailure']['message'])
        self.assertTrue(receipt['errors'])
        self.assertTrue(receipt['uncertainResourcesPreserved'])
        self.assertFalse(receipt['normalFixtureDisposalProven'])
        self.assertEqual(resources,len(receipt['resources']))
        return receipt

    def test_remaining_container_refused(self):
        self.remaining=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Owned helper/container remains')

    def test_remaining_volume_refused(self):
        self.volume_remaining=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Provider volume remains')

    def test_preexisting_volume_refused(self):
        self.preexisting=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Unexpected or preexisting persistent mount')

    def test_wrong_session_refused(self):
        self.session_mismatch=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Providers belong to different sessions')

    def test_missing_disposal_log_refused(self):
        self.missing_log=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Provider IDs not bound')

    def test_missing_destroy_event_refused(self):
        self.missing_event=True
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Missing ordered provider lifecycle events')

    def test_actual_start_not_observed_refused(self):
        self.metadata[self.container_ids[0]]['State']['StartedAt']='0001-01-01T00:00:00Z'
        with self.assertRaises(ValueError):self.run_observer()
        self.assert_refused_receipt('Provider start time not observed')

    def test_timeout_preserves_receipt(self):
        self.timeout=True
        with self.assertRaises(ValueError):self.run_observer()
        receipt=json.loads((self.output/'provider-observation.json').read_text())
        self.assertEqual('ValueError',receipt['primaryFailure']['category'])
        self.assertIn('timed out',receipt['primaryFailure']['message'])

    def test_cleanup_exception_preserves_primary_failure(self):
        self.timeout=True;self.cleanup_failure=True
        with self.assertRaises(ValueError):self.run_observer()
        receipt=json.loads((self.output/'provider-observation.json').read_text())
        self.assertIn('timed out',receipt['primaryFailure']['message'])
        self.assertTrue(any('cleanup failure' in x for x in receipt['errors']))

    def test_error_path_preserves_already_observed_provider_metadata(self):
        self.inspect_failure=True
        with self.assertRaises(OSError):self.run_observer()
        receipt=json.loads((self.output/'provider-observation.json').read_text())
        self.assertEqual('OSError',receipt['primaryFailure']['category'])
        self.assertEqual(1,len(receipt['resources']))
        self.assertTrue(receipt['uncertainResourcesPreserved'])
        self.assertNotIn('secret-canary',json.dumps(receipt))

    def test_missing_session_and_launcher_wait_failure_retains_receipt(self):
        self.custody_failure=True;self.wait_failure=True
        with self.assertRaises(OSError):self.run_observer()
        receipt=json.loads((self.output/'provider-observation.json').read_text())
        self.assertIn('custody failure',receipt['primaryFailure']['message'])
        self.assertTrue(any('terminate failure' in x for x in receipt['errors']))
        self.assertTrue(any('launcher wait:' in x for x in receipt['errors']))
        self.assertTrue(self.killed);self.assertTrue(receipt['processExited'])

    def test_initial_docker_failure_writes_refusal_receipt_without_launcher(self):
        self.initial_docker_failure=True
        with self.assertRaises(OSError):self.run_observer()
        receipt=self.assert_refused_receipt('synthetic initial Docker failure',resources=0)
        self.assertIsNone(receipt['processSessionCleanup'])
        self.assertNotIn('processIdentity',receipt)

    def test_initial_volume_failure_writes_refusal_receipt_without_launcher(self):
        self.initial_volume_failure=True
        with self.assertRaises(OSError):self.run_observer()
        receipt=self.assert_refused_receipt('synthetic initial volume failure',resources=0)
        self.assertIsNone(receipt['processSessionCleanup'])
        self.assertNotIn('processIdentity',receipt)


class OwnedSessionControls(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(processes.signal,'SIGKILL',9,create=True)
        patcher.start();self.addCleanup(patcher.stop)

    def identities(self):
        return [{'processId':10,'sessionId':10,'processGroupId':10,'startClockTicks':'100','executable':'synthetic-parent'},
                {'processId':11,'sessionId':10,'processGroupId':10,'startClockTicks':'101','executable':'synthetic-child'}]

    def fake_session(self):
        process=unittest.mock.Mock(pid=10)
        process.poll.return_value=0
        with patch.object(processes.sys,'platform','linux'),patch.object(processes.os,'pidfd_open',return_value=50,create=True),patch.object(processes.signal,'pidfd_send_signal',create=True),patch.object(processes,'process_identity',return_value=self.identities()[0]):
            session=processes.OwnedSession(process)
        session.handles={10:{'fd':50,'identity':self.identities()[0]},11:{'fd':51,'identity':self.identities()[1]}}
        return session

    def test_signal_failure_still_attempts_every_owned_member_and_closes_handles(self):
        session=self.fake_session()
        with patch.object(session,'capture'),patch.object(session,'_settle'),patch.object(processes,'ready',return_value=False),patch.object(processes.signal,'pidfd_send_signal',side_effect=OSError('synthetic signal denial'),create=True) as send,patch.object(processes,'session_members',return_value=self.identities()),patch.object(processes.os,'close') as close:
            proof=session.cleanup(failed=True)
        self.assertEqual([51,50,51,50],[call.args[0] for call in send.call_args_list])
        self.assertEqual({50,51},{call.args[0] for call in close.call_args_list})
        self.assertFalse(proof['verified']);self.assertTrue(proof['handlesClosed'])

    def test_wait_failure_retains_proof_and_closes_handles(self):
        session=self.fake_session();session.process.wait.side_effect=subprocess.TimeoutExpired('synthetic',3)
        with patch.object(session,'capture'),patch.object(session,'_settle'),patch.object(processes,'ready',return_value=True),patch.object(processes,'session_members',return_value=[]),patch.object(processes.os,'close') as close:
            proof=session.cleanup()
        self.assertFalse(proof['verified']);self.assertTrue(any('wait:' in x for x in proof['cleanupErrors']))
        self.assertEqual(2,close.call_count)

    def test_pid_reuse_is_refused_without_signaling(self):
        session=self.fake_session();changed=self.identities();changed[0]['startClockTicks']='999'
        with patch.object(processes,'session_members',return_value=changed),patch.object(processes.signal,'pidfd_send_signal',create=True) as send:
            with self.assertRaises(ValueError):session.capture()
            send.assert_not_called()

    def test_capture_failure_still_attempts_retained_members(self):
        session=self.fake_session()
        with patch.object(session,'capture',side_effect=OSError('synthetic capture failure')),patch.object(session,'_settle'),patch.object(processes,'ready',return_value=False),patch.object(processes.signal,'pidfd_send_signal',create=True) as send,patch.object(processes,'session_members',return_value=self.identities()),patch.object(processes.os,'close') as close:
            proof=session.cleanup(failed=True)
        self.assertEqual([51,50,51,50],[call.args[0] for call in send.call_args_list])
        self.assertFalse(proof['verified']);self.assertEqual(2,close.call_count)

    def test_member_naturally_exited_before_pidfd_open_is_retained_as_observation(self):
        session=self.fake_session();members=self.identities()+[{'processId':12,'sessionId':10,'processGroupId':10,'startClockTicks':'102','executable':'synthetic-transient'}]
        with patch.object(processes,'session_members',return_value=members),patch.object(processes,'ready',return_value=False),patch.object(processes.os,'pidfd_open',side_effect=ProcessLookupError('synthetic exited member'),create=True):
            session.capture()
        self.assertEqual([12],[x['processId'] for x in session.exited_before_binding])
        self.assertEqual({10,11},set(session.handles))

    def test_close_failure_still_attempts_every_handle(self):
        session=self.fake_session()
        def close_fd(fd):
            if fd==50:raise OSError('synthetic close failure')
        with patch.object(session,'capture'),patch.object(session,'_settle'),patch.object(processes,'ready',return_value=True),patch.object(processes,'session_members',return_value=[]),patch.object(processes.os,'close',side_effect=close_fd) as close:
            proof=session.cleanup()
        self.assertEqual(2,close.call_count)
        self.assertFalse(proof['verified']);self.assertFalse(proof['handlesClosed'])

    @unittest.skipUnless(sys.platform.startswith('linux'),'Actual Linux pidfd/session smoke NOT RUN on Windows')
    def test_actual_linux_launcher_and_child_exit_under_retained_pidfds(self):
        processes.require(hasattr(processes.os,'pidfd_open') and hasattr(processes.signal,'pidfd_send_signal'),'Preflight Linux pidfd APIs before launching smoke')
        receipt={}
        self.run_launcher_smoke(receipt)
        self.assertTrue(receipt['processExited']);self.assertTrue(receipt['pipesClosed'])

    def run_launcher_smoke(self, receipt):
        process=None;session=None
        try:
            # Child cannot start before custody is established. EOF/3s timeout exits
            # the launcher; even after authorization the child has a finite3s lease.
            process=subprocess.Popen([sys.executable,'-c',"import select,subprocess,sys; ready=select.select([sys.stdin],[],[],3)[0]; permitted=bool(ready) and sys.stdin.readline()=='go\\n'; child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3)']) if permitted else None; print(child.pid,flush=True) if child else None; child.wait() if child else None"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,start_new_session=True)
            receipt.update(launcherPid=process.pid,childAuthorized=False,uncertainResourcesPreserved=True,finiteLeaseSeconds=6)
            session=processes.OwnedSession(process)
            process.stdin.write('go\n');process.stdin.flush();receipt['childAuthorized']=True
            readable=processes.select.select([process.stdout],[],[],3)[0]
            self.assertTrue(readable,'Bounded child creation witness missing')
            child_id=int(process.stdout.readline())
            session.capture()
            self.assertIn(child_id,session.handles)
            proof=session.cleanup(failed=True)
            receipt['cleanup']=proof
            self.assertTrue(proof['verified'],proof)
            self.assertTrue(proof['handlesClosed']);self.assertTrue(proof['forcedCleanup'])
            self.assertEqual([],processes.session_members(process.pid))
        except BaseException as error:
            receipt['primaryFailure']=type(error).__name__+': '+str(error)
            raise
        finally:
            if process is not None:
                cleanup_errors=[]
                try:
                    if session is not None and process.poll() is None:receipt['cleanup']=session.cleanup(failed=True)
                except BaseException as error:cleanup_errors.append('session: '+str(error))
                for pipe in (process.stdin,process.stdout):
                    try:pipe.close()
                    except BaseException as error:cleanup_errors.append('pipe: '+str(error))
                try:process.wait(timeout=8)
                except BaseException as error:cleanup_errors.append('wait: '+str(error))
                receipt.update(processExited=process.poll() is not None,pipesClosed=process.stdin.closed and process.stdout.closed,cleanupErrors=cleanup_errors)
                receipt['uncertainResourcesPreserved']=bool(cleanup_errors) or not receipt['processExited'] or (receipt['childAuthorized'] and not receipt.get('cleanup',{}).get('verified',False))

    def test_smoke_constructor_refusal_closes_pipes_without_authorizing_child(self):
        process=Mock();process.pid=42;process.poll.return_value=0
        process.stdin.closed=True;process.stdout.closed=True;receipt={}
        with patch.object(subprocess,'Popen',return_value=process),patch.object(processes,'OwnedSession',side_effect=ValueError('synthetic custody refusal')):
            with self.assertRaisesRegex(ValueError,'synthetic custody refusal'):self.run_launcher_smoke(receipt)
        process.stdin.write.assert_not_called();process.stdin.close.assert_called_once();process.stdout.close.assert_called_once();process.wait.assert_called_once_with(timeout=8)
        self.assertFalse(receipt['childAuthorized']);self.assertTrue(receipt['pipesClosed']);self.assertTrue(receipt['processExited']);self.assertIn('custody refusal',receipt['primaryFailure'])


if __name__=='__main__':unittest.main()
