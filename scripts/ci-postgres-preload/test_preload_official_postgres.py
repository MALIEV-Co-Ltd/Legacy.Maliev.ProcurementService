import copy,json,unittest
from pathlib import Path
import preload_official_postgres as p
R=Path(__file__).resolve().parent
class Controls(unittest.TestCase):
 def setUp(self):
  self.row=json.loads((R/'image-pins.json').read_bytes())[0];self.tag=self.row['tag'].split(':')[1]
  self.index=(R/(self.tag+'-index.json')).read_bytes();self.manifest=(R/(self.tag+'-manifest.json')).read_bytes()
  self.hub=json.dumps({'digest':self.row['indexDigest'],'images':[{'os':'linux','architecture':'amd64','digest':self.row['manifestDigest']}]}).encode()
  self.ins={'Id':self.row['configDigest'],'Os':'linux','Architecture':'amd64','RepoDigests':[self.row['mirror']]}
 def test_exact(self):p.validate(self.row,self.hub,self.index,self.manifest);p.inspect_ok(self.row,self.ins)
 def test_index(self):
  with self.assertRaises(ValueError):p.validate(self.row,self.hub,self.index+b' ',self.manifest)
 def test_manifest(self):
  with self.assertRaises(ValueError):p.validate(self.row,self.hub,self.index,self.manifest+b' ')
 def test_hub(self):
  h=json.loads(self.hub);h['digest']='sha256:'+'0'*64
  with self.assertRaises(ValueError):p.validate(self.row,json.dumps(h).encode(),self.index,self.manifest)
 def test_platform(self):
  h=json.loads(self.hub);h['images'][0]['architecture']='arm64'
  with self.assertRaises(ValueError):p.validate(self.row,json.dumps(h).encode(),self.index,self.manifest)
 def test_config(self):
  row=copy.deepcopy(self.row);row['configDigest']='sha256:'+'0'*64
  with self.assertRaises(ValueError):p.validate(row,self.hub,self.index,self.manifest)
 def test_layers(self):
  row=copy.deepcopy(self.row);row['layers'][0]['size']+=1
  with self.assertRaises(ValueError):p.validate(row,self.hub,self.index,self.manifest)
 def test_engine(self):
  for key,value in [('Id','wrong'),('Os','windows'),('Architecture','arm64'),('RepoDigests',[])]:
   with self.subTest(key=key):
    item=copy.deepcopy(self.ins);item[key]=value
    with self.assertRaises(ValueError):p.inspect_ok(self.row,item)
 def scenario(self,mode):
  calls=[];created=[];saved=[]
  def metadata(row):return self.hub if mode!='metadata-fail' else b'{}',self.index,self.manifest
  def run(args,required=True):
   calls.append(args)
   if args[1:3]==['image','inspect']:
    if args[-1]==self.row['mirror'] and mode=='pull-fail':return None
    if args[-1]==self.row['tag'] and not created:
     if mode=='foreign':return json.dumps([dict(self.ins,Id='foreign')]).encode()
     if mode=='cache':return json.dumps([self.ins]).encode()
     return None
    return json.dumps([self.ins]).encode()
   if args[1]=='pull' and mode=='pull-fail':raise RuntimeError('pull failed')
   if args[1]=='tag':created.append(args[-1])
   return b''
  receipt={'createdTags':[],'write':lambda:saved.append(True)}
  return calls,created,saved,lambda:p.preload([self.row],run,receipt,metadata)
 def test_preload(self):
  calls,created,saved,invoke=self.scenario('success');invoke();self.assertEqual(created,[self.row['tag']]);self.assertEqual(len(saved),2)
 def test_existing_cache(self):
  calls,created,saved,invoke=self.scenario('cache');invoke();self.assertFalse(created);self.assertEqual(len(calls),1)
 def test_foreign_preserved(self):
  calls,created,saved,invoke=self.scenario('foreign')
  with self.assertRaises(ValueError):invoke()
  self.assertFalse(created);self.assertFalse(any(c[1]=='pull' for c in calls))
 def test_pull_failure_no_retag(self):
  calls,created,saved,invoke=self.scenario('pull-fail')
  with self.assertRaises(RuntimeError):invoke()
  self.assertFalse(created)
 def test_metadata_before_mutation(self):
  calls,created,saved,invoke=self.scenario('metadata-fail')
  with self.assertRaises(KeyError):invoke()
  self.assertFalse(calls)
 def test_partial_pull_timeout_journaled(self):self.partial('pull',TimeoutError('partial pull'))
 def test_partial_tag_timeout_journaled(self):self.partial('tag',TimeoutError('partial tag'))
 def test_partial_pull_nonzero_journaled(self):self.partial('pull',RuntimeError('partial pull'))
 def test_partial_tag_nonzero_journaled(self):self.partial('tag',RuntimeError('partial tag'))
 def partial(self,verb,primary):
  snapshots=[];created=[];receipt={'createdTags':[],'write':lambda:snapshots.append(copy.deepcopy(receipt['createdTags']))}
  def run(args,required=True):
   if args[1]==verb:
    self.assertEqual(snapshots[-1][0]['state'],'intent');created.append(True);raise primary
   return json.dumps([self.ins]).encode() if created else None
  with self.assertRaises(type(primary)) as caught:p.mutate(['docker',verb],self.row['tag'],self.row,run,receipt)
  self.assertIs(caught.exception,primary);self.assertEqual(snapshots[-1][0]['state'],'exact-reference-observed')
 def test_prejournal_write_failure_prevents_mutation(self):
  calls=[];receipt={'createdTags':[],'write':lambda:(_ for _ in ()).throw(OSError('disk'))}
  with self.assertRaises(OSError):p.mutate(['docker','tag'],self.row['tag'],self.row,lambda *a:calls.append(a),receipt)
  self.assertFalse(calls)
 def test_secondary_write_preserves_primary(self):
  primary=TimeoutError('daemon');writes=[]
  def save():
   writes.append(True)
   if len(writes)>1:raise OSError('disk')
  def run(args,required=True):
   if args[1]=='tag':raise primary
   return json.dumps([self.ins]).encode()
  with self.assertRaises(TimeoutError) as caught:p.mutate(['docker','tag'],self.row['tag'],self.row,run,{'createdTags':[],'write':save})
  self.assertIs(caught.exception,primary);self.assertTrue(primary.__notes__)
 def test_final_save_preserves_primary(self):
  primary=ValueError('original')
  with self.assertRaises(ValueError) as caught:p.preserve_primary(lambda:(_ for _ in ()).throw(primary),lambda:(_ for _ in ()).throw(OSError('disk')))
  self.assertIs(caught.exception,primary)
 def cleanup_scenario(self,mode):
  entries=[{'tag':tag,'configDigest':self.row['configDigest'],'preExisting':False,'state':'intent','commandSettled':True} for tag in ('independent','blocked')];removed=[];saved=[]
  def run(args,required=True):
   if args[1:3]==['image','inspect']:
    if args[-1] in removed:return None
    return json.dumps([dict(self.ins,Id='foreign' if args[-1]=='blocked' and mode=='foreign' else self.ins['Id'])]).encode()
   if args[1]=='ps':return b'active' if mode=='active' and not removed and entries[1]['state']!='absent' else b''
   if args[1:3]==['image','rm']:
    if args[-1]=='blocked' and mode=='remove-fail':raise RuntimeError('remove')
    removed.append(args[-1])
   return b''
  def save():
   saved.append(True)
   if mode=='save-fail':raise OSError('disk')
  return entries,removed,saved,lambda:p.cleanup({'createdTags':entries},run,save)
 def test_cleanup_foreign_continues(self):
  entries,removed,saved,invoke=self.cleanup_scenario('foreign')
  with self.assertRaises(ExceptionGroup):invoke()
  self.assertEqual(removed,['independent']);self.assertEqual(len(saved),2)
 def test_cleanup_remove_failure_continues(self):
  entries,removed,saved,invoke=self.cleanup_scenario('remove-fail')
  with self.assertRaises(ExceptionGroup):invoke()
  self.assertEqual(removed,['independent'])
 def test_actual_cached_metadata_all_three(self):
  for row in json.loads((R/'image-pins.json').read_bytes()):p.validate(row,*p.read_metadata(row))
 def test_cached_hub_digest_tamper(self):
  row=copy.deepcopy(self.row);row['hubMetadataSha256']='0'*64
  with self.assertRaises(ValueError):p.read_metadata(row)
 def test_cached_hub_length_tamper(self):
  row=copy.deepcopy(self.row);row['hubMetadataBytes']+=1
  with self.assertRaises(ValueError):p.read_metadata(row)
 def test_metadata_acquisition_requires_no_http(self):
  from unittest.mock import patch
  import urllib.request
  with patch.object(urllib.request,'urlopen',side_effect=AssertionError('HTTP forbidden')),patch.object(urllib.request.OpenerDirector,'open',side_effect=AssertionError('HTTP forbidden')):
   p.preload([self.row],lambda *args:json.dumps([self.ins]).encode(),{'createdTags':[],'write':lambda:None})
 def test_cached_index_tamper_before_any_docker(self):
  calls=[]
  with self.assertRaises(ValueError):p.preload([self.row],lambda *args:calls.append(args),{'createdTags':[],'write':lambda:None},lambda row:(self.hub,self.index+b' ',self.manifest))
  self.assertFalse(calls)
 def test_cached_manifest_tamper_before_any_docker(self):
  calls=[]
  with self.assertRaises(ValueError):p.preload([self.row],lambda *args:calls.append(args),{'createdTags':[],'write':lambda:None},lambda row:(self.hub,self.index,self.manifest+b' '))
  self.assertFalse(calls)
 def test_late_daemon_mutation_never_discharges_intent(self):
  entry={'tag':'late','configDigest':self.row['configDigest'],'preExisting':False,'state':'intent','commandSettled':False};daemon={'present':False};saved=[];removed=[]
  def run(args,required=True):
   if args[1:3]==['image','inspect']:return json.dumps([self.ins]).encode() if daemon['present'] else None
   if args[1:3]==['image','rm']:daemon['present']=False;removed.append(args[-1])
   return b''
  data={'createdTags':[entry]}
  with self.assertRaises(ExceptionGroup):p.cleanup(data,run,lambda:saved.append(copy.deepcopy(entry)))
  self.assertEqual(entry['state'],'absence-unsettled');self.assertTrue(entry['unresolvedDaemonOperation'])
  daemon['present']=True # The daemon completes after the first absent observation.
  with self.assertRaises(ExceptionGroup):p.cleanup(data,run,lambda:saved.append(copy.deepcopy(entry)))
  self.assertEqual(removed,['late']);self.assertEqual(entry['state'],'absence-unsettled');self.assertFalse(entry['commandSettled'])
 def test_unsettled_absence_does_not_block_independent_cleanup(self):
  pending={'tag':'late','configDigest':self.row['configDigest'],'preExisting':False,'state':'intent','commandSettled':False}
  settled=dict(pending,tag='independent',commandSettled=True);removed=[]
  def run(args,required=True):
   if args[1:3]==['image','inspect']:return None if args[-1]=='late' or args[-1] in removed else json.dumps([self.ins]).encode()
   if args[1:3]==['image','rm']:removed.append(args[-1])
   return b''
  with self.assertRaises(ExceptionGroup):p.cleanup({'createdTags':[settled,pending]},run,lambda:None)
  self.assertEqual(removed,['independent']);self.assertEqual(settled['state'],'absent');self.assertEqual(pending['state'],'absence-unsettled')
 def test_cleanup_write_failure_continues(self):
  entries,removed,saved,invoke=self.cleanup_scenario('save-fail')
  with self.assertRaises(ExceptionGroup):invoke()
  self.assertEqual(removed,['blocked','independent'])
 def test_cleanup_missing_reconciles(self):
  entry={'tag':'missing','configDigest':self.row['configDigest'],'preExisting':False,'state':'intent','commandSettled':True}
  p.cleanup({'createdTags':[entry]},lambda *args:None,lambda:None);self.assertEqual(entry['state'],'absent')
 def test_atomic_receipt_real_file(self):
  import tempfile
  with tempfile.TemporaryDirectory() as root:
   file=Path(root)/'receipt.json';p.atomic_save(file,{'createdTags':[]});self.assertEqual(json.loads(file.read_bytes()),{'createdTags':[]});self.assertFalse(file.with_suffix('.pending').exists())
 def test_atomic_preexisting_pending_preserved(self):
  import tempfile
  with tempfile.TemporaryDirectory() as root:
   file=Path(root)/'receipt.json';pending=file.with_suffix('.pending');pending.write_bytes(b'foreign')
   with self.assertRaises(FileExistsError):p.atomic_save(file,{})
   self.assertEqual(pending.read_bytes(),b'foreign');self.assertFalse(file.exists())
 def test_real_journal_partial_pull_timeout(self):self.real_journal_partial('pull')
 def test_real_journal_partial_tag_timeout(self):self.real_journal_partial('tag')
 def real_journal_partial(self,verb):
  import tempfile
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'receipt.json';data={'createdTags':[]};created=[]
   receipt={'createdTags':data['createdTags'],'write':lambda:p.atomic_save(path,data)}
   def run(args,required=True):
    if args[1]==verb:
     recorded=json.loads(path.read_bytes());self.assertEqual(recorded['createdTags'][0]['state'],'intent')
     created.append(True);raise TimeoutError('daemon mutated before client timed out')
    return json.dumps([self.ins]).encode() if created else None
   with self.assertRaises(TimeoutError):p.mutate(['docker',verb],self.row['tag'],self.row,run,receipt)
   self.assertEqual(json.loads(path.read_bytes())['createdTags'][0]['state'],'exact-reference-observed')
 def test_cleanup_active_reference_continues(self):
  entries=[{'tag':tag,'configDigest':self.row['configDigest'],'preExisting':False,'state':'intent','commandSettled':True} for tag in ('independent','active')];last=[];removed=[]
  def run(args,required=True):
   if args[1:3]==['image','inspect']:
    last[:]=[args[-1]]
    return None if args[-1] in removed else json.dumps([self.ins]).encode()
   if args[1]=='ps':return b'client' if last==['active'] else b''
   if args[1:3]==['image','rm']:removed.append(args[-1])
   return b''
  with self.assertRaises(ExceptionGroup):p.cleanup({'createdTags':entries},run,lambda:None)
  self.assertEqual(removed,['independent'])
class DockerDiagnostics(unittest.TestCase):
 def setUp(self):self.image=json.loads((R/'image-pins.json').read_bytes())[0]['mirror']
 def test_known_category_and_explicit_status(self):
  payload=b'HTTP 429: toomanyrequests';error=p.command_failure(['docker','pull',self.image],1,payload,len(payload))
  self.assertEqual(error.diagnostic['category'],'registry-rate-limit');self.assertEqual(error.diagnostic['explicitHttpStatus'],429)
 def test_unknown_secret_canary_never_disclosed(self):
  secret=b'CANARY-DO-NOT-DISCLOSE password=secret https://host/path?token=secret'
  error=p.command_failure(['docker','pull','foreign?token=secret'],1,secret,len(secret))
  encoded=json.dumps(error.diagnostic)+str(error)
  self.assertNotIn('CANARY',encoded);self.assertNotIn('password',encoded);self.assertNotIn('token=',encoded)
  self.assertEqual(error.diagnostic['category'],'unknown');self.assertIsNone(error.diagnostic['imageReference'])
 def test_prefix_hash_and_truncation_are_explicit(self):
  import hashlib
  prefix=b'x'*4096;error=p.command_failure(['docker','pull',self.image],1,prefix,9000)
  self.assertTrue(error.diagnostic['truncated']);self.assertEqual(error.diagnostic['capturedBytes'],4096)
  self.assertEqual(error.diagnostic['stderrBytes'],9000);self.assertEqual(error.diagnostic['hashScope'],'captured-prefix')
  self.assertEqual(error.diagnostic['sha256'],hashlib.sha256(prefix).hexdigest())
  with self.assertRaises(ValueError):p.command_failure(['docker','pull',self.image],1,b'x'*4097,4097)
 def test_mutation_preserves_diagnostic_primary_and_unsettled_intent(self):
  row=json.loads((R/'image-pins.json').read_bytes())[0];error=p.command_failure(['docker','pull',self.image],1,b'pull access denied',18)
  receipt={'createdTags':[],'write':lambda:None}
  def run(args,required=True):
   if args[1]=='pull':raise error
   return None
  with self.assertRaises(p.DockerCommandFailure) as caught:p.mutate(['docker','pull',self.image],self.image,row,run,receipt)
  self.assertIs(caught.exception,error);entry=receipt['createdTags'][0]
  self.assertEqual(entry['failureDiagnostic'],error.diagnostic);self.assertFalse(entry['commandSettled']);self.assertEqual(entry['state'],'absence-unsettled')
 def test_actual_main_bounds_diagnostic_prefix(self):self.main_boundary(False)
 def test_actual_main_timeout_preserves_primary(self):self.main_boundary(True)
 def main_boundary(self,timeout):
  import tempfile,os,subprocess
  from unittest.mock import patch
  handles=[];row=json.loads((R/'image-pins.json').read_bytes())[0];primary=subprocess.TimeoutExpired(['docker','pull',self.image],1)
  def invoke(rows,run,receipt,metadata=None):p.mutate(['docker','pull',self.image],self.image,row,run,receipt)
  def command(args,timeout,hard_deadline=None):
   if args[1]=='pull':
    if failure_timeout:raise primary
    return subprocess.CompletedProcess(args,1,b'',b'x'*4096),9032
   return subprocess.CompletedProcess(args,1,b'',b'No such image'),13
  failure_timeout=timeout
  with tempfile.TemporaryDirectory() as root:
   with patch.dict(os.environ,{'RUNNER_TEMP':root}),patch.object(p,'preload',side_effect=invoke),patch.object(p,'run_docker_cli',side_effect=command),patch('sys.argv',['preload_official_postgres.py']):
    with self.assertRaises(subprocess.TimeoutExpired if timeout else p.DockerCommandFailure) as caught:p.main()
   if timeout:self.assertIs(caught.exception,primary)
   entry=json.loads((Path(root)/'procurement-postgres-preload.json').read_bytes())['createdTags'][0]
   self.assertFalse(entry['commandSettled']);self.assertEqual(entry['state'],'absence-unsettled')
   self.assertNotIn('CANARY',(Path(root)/'procurement-postgres-preload.json').read_text())
   if not timeout:
    self.assertEqual(entry['failureDiagnostic']['capturedBytes'],4096);self.assertTrue(entry['failureDiagnostic']['truncated'])
class LiveCaptureControls(unittest.TestCase):
 def test_stderr_storage_is_bounded_while_counting_stream(self):
  c=p.DockerCapture()
  for _ in range(1000):c.feed('stderr',b'x'*4096)
  self.assertEqual(len(c.stderr),4096);self.assertEqual(c.stderr_bytes,4096000)
 def test_stdout_pressure_fails_before_growing_past_cap(self):
  c=p.DockerCapture()
  for _ in range(256):c.feed('stdout',b'x'*4096)
  with self.assertRaisesRegex(RuntimeError,'limit'):c.feed('stdout',b'x')
  self.assertEqual(len(c.stdout),1048576)
 def test_capture_and_chunk_faults_preserve_process_primary(self):self.adapter_fault('capture')
 def test_deadline_plus_all_close_faults_preserves_timeout(self):self.adapter_fault('deadline',close_faults=True)
 def test_registration_failure_closes_both_unregistered_pipes(self):self.adapter_fault('register')
 def test_ignored_graceful_stop_uses_exact_handle_kill_and_wait(self):self.adapter_fault('grace-timeout')
 def test_kill_failure_preserves_primary_and_closes_independent_handles(self):self.adapter_fault('kill-failure')
 def test_exhausted_recovery_does_not_renew_budget_or_erase_child(self):self.adapter_fault('budget-expiry')
 def adapter_fault(self,mode,close_faults=False):
  import subprocess,types,selectors
  from unittest.mock import patch
  primary=OSError('actual capture/register failure');closed=[];events=[];settled=[]
  class Pipe:
   def __init__(self,name):self.name=name
   def fileno(self):return 11 if self.name=='stdout' else 12
   def close(self):
    closed.append(self.name)
    if close_faults:raise OSError('close')
  class Process:
   stdout=Pipe('stdout');stderr=Pipe('stderr')
   returncode=None
   def poll(self):return self.returncode
   def terminate(self):
    events.append('terminate')
    if mode not in ('grace-timeout','kill-failure'):self.returncode=0
   def kill(self):
    events.append('kill')
    if mode=='kill-failure':raise OSError('kill')
    self.returncode=-9
   def wait(self,timeout):
    settled.append(timeout)
    if self.returncode is None:raise subprocess.TimeoutExpired(['docker'],timeout)
    return self.returncode
  class Selector:
   def register(self,*args):
    if mode=='register':raise primary
   def get_map(self):return {'owned':True}
   def select(self,timeout):return [(types.SimpleNamespace(fd=11,data='stdout',fileobj=None),1)]
   def close(self):
    closed.append('selector')
    if close_faults:raise OSError('close')
  clocks=[0]+[3]*20 if mode=='deadline' else [0,0]+[6]*20 if mode=='budget-expiry' else [0]*20
  with patch('os.name','posix'),patch.object(p.subprocess,'Popen',return_value=Process()),patch.object(selectors,'DefaultSelector',return_value=Selector()),patch('os.set_blocking'),patch('os.read',side_effect=primary),patch.object(p.time,'monotonic',side_effect=clocks):
   with self.assertRaises(subprocess.TimeoutExpired if mode=='deadline' else OSError) as caught:p.run_docker_cli(['docker','pull',json.loads((R/'image-pins.json').read_bytes())[0]['mirror']],5)
  if mode!='deadline':self.assertIs(caught.exception,primary)
  else:self.assertTrue(caught.exception.__notes__)
  self.assertEqual(closed,['selector','stdout','stderr']);self.assertEqual(events,[] if mode=='budget-expiry' else ['terminate','kill'] if mode in ('grace-timeout','kill-failure') else ['terminate'])
  if mode=='budget-expiry':
   self.assertFalse(settled);self.assertFalse(caught.exception.owned_cli_resource['exitConfirmed']);self.assertTrue(caught.exception.__notes__)
  else:self.assertTrue(settled)
  if mode=='kill-failure':self.assertTrue(caught.exception.__notes__)
 @unittest.skipUnless(__import__('os').name=='posix','Actual selector pipe proof requires Linux hosted runner')
 def test_real_both_pipe_streams_and_stdout_limit(self):
  import subprocess,sys
  from unittest.mock import patch
  original=p.subprocess.Popen;children=[]
  def launch(args,**kwargs):
   child=original([sys.executable,'-c',"import sys;sys.stderr.buffer.write(b'x'*20000);sys.stdout.buffer.write(b'ok')"],**kwargs);children.append(child);return child
  with patch.object(p.subprocess,'Popen',side_effect=launch):
   result,total=p.run_docker_cli(['docker','pull',json.loads((R/'image-pins.json').read_bytes())[0]['mirror']],6)
  self.assertEqual(result.stdout,b'ok');self.assertEqual(len(result.stderr),4096);self.assertEqual(total,20000)
  self.assertTrue(all(child.poll() is not None and child.stdout.closed and child.stderr.closed for child in children))
 def test_reserve_required_before_birth(self):
  from unittest.mock import patch
  with patch('os.name','posix'),patch.object(p.time,'monotonic',return_value=0),patch.object(p.subprocess,'Popen') as launch:
   with self.assertRaisesRegex(TimeoutError,'before process birth'):p.run_docker_cli(['docker'],3)
   launch.assert_not_called()
 def test_original_parent_hard_deadline_is_not_extended(self):
  from unittest.mock import patch
  with patch('os.name','posix'),patch.object(p.time,'monotonic',return_value=10),patch.object(p.subprocess,'Popen') as launch:
   with self.assertRaises(TimeoutError):p.run_docker_cli(['docker'],90,hard_deadline=12)
   launch.assert_not_called()
if __name__=='__main__':unittest.main()
