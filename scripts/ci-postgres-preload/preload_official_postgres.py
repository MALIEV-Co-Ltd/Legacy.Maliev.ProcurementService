"""Bounded ordinary-CI image preparation; never starts containers."""
import hashlib,json,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args):raise ValueError('Registry redirect refused')
def fetch(url,token=None):
 headers={'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/json'}
 if token:headers['Authorization']='Bearer '+token
 with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,headers=headers),timeout=12) as r:return r.read()
def digest(raw):return 'sha256:'+hashlib.sha256(raw).hexdigest()
def validate(row,hub,index,manifest):
 if digest(index)!=row['indexDigest'] or digest(manifest)!=row['manifestDigest']:raise ValueError('Immutable manifest drift')
 h=json.loads(hub);i=json.loads(index);m=json.loads(manifest)
 hp=[p for p in h['images'] if p.get('os')=='linux' and p.get('architecture')=='amd64']
 ip=[p for p in i['manifests'] if p.get('platform',{}).get('os')=='linux' and p.get('platform',{}).get('architecture')=='amd64']
 if h['digest']!=row['indexDigest'] or len(hp)!=1 or hp[0]['digest']!=row['manifestDigest']:raise ValueError('Original Hub tag drift')
 if len(ip)!=1 or ip[0]['digest']!=row['manifestDigest']:raise ValueError('Platform association drift')
 if m['config']['digest']!=row['configDigest'] or m['layers']!=row['layers']:raise ValueError('Config or layer descriptor drift')
def inspect_ok(row,value):
 if value.get('Id')!=row['configDigest'] or value.get('Os')!='linux' or value.get('Architecture')!='amd64':raise ValueError('Engine image identity drift')
 if not any(d.endswith('@'+row['indexDigest']) or d.endswith('@'+row['manifestDigest']) for d in value.get('RepoDigests',[])):raise ValueError('Engine manifest association missing')
def preserve_primary(operation,save):
 try:return operation()
 except BaseException as primary:
  try:save()
  except BaseException as secondary:primary.add_note('Secondary receipt failure: '+type(secondary).__name__)
  raise
def reconcile(entry,run):
 raw=run(['docker','image','inspect',entry['tag']],False)
 if raw is None:
  entry['state']='absent' if entry.get('commandSettled') else 'absence-unsettled'
  return
 if json.loads(raw)[0]['Id']!=entry['configDigest']:
  entry['state']='foreign-preserved';raise ValueError('Preserve replaced image reference')
 entry['state']='exact-reference-observed'
def mutate(args,tag,row,run,receipt):
 # This durable intent precedes the daemon command, including failure/timeout paths.
 entry={'tag':tag,'configDigest':row['configDigest'],'preExisting':False,'state':'intent','commandSettled':False,'unresolvedLease':'until this finite ephemeral hosted job runner is destroyed; external confirmation required'}
 receipt['createdTags'].append(entry);receipt['write']()
 try:
  run(args);entry['commandSettled']=True;reconcile(entry,run)
  if entry['state']!='exact-reference-observed':raise ValueError('Daemon mutation not observed')
 except BaseException as primary:
  try:reconcile(entry,run)
  except BaseException as secondary:primary.add_note('Secondary reconciliation failure: '+type(secondary).__name__)
  try:receipt['write']()
  except BaseException as secondary:primary.add_note('Secondary receipt failure: '+type(secondary).__name__)
  raise
 receipt['write']()
def cleanup(data,run,save):
 errors=[]
 for entry in reversed(data['createdTags']):
  try:
   if entry.get('preExisting') is not False:raise ValueError('Unproven reference ownership')
   reconcile(entry,run)
   if entry['state'] not in ('absent','absence-unsettled'):
    if run(['docker','ps','-q','--filter','ancestor='+entry['configDigest']]).strip():raise ValueError('Preserve active image')
    reconcile(entry,run)
    if entry['state'] not in ('absent','absence-unsettled'):run(['docker','image','rm','--no-prune',entry['tag']])
    reconcile(entry,run)
    if entry['state'] not in ('absent','absence-unsettled'):raise ValueError('Reference cleanup not confirmed')
   if entry.get('commandSettled') is not True:
    entry['unresolvedDaemonOperation']=True
    raise RuntimeError('Daemon mutation completion unproven; absence does not discharge intent or lease')
  except Exception as error:errors.append(error)
  try:save()
  except Exception as error:errors.append(error)
 # Recover independent references even if one reference/receipt failed.
 if errors:raise ExceptionGroup('Image cleanup failures; unresolved references preserved',errors)
def preload(rows,run,network,receipt):
 # Verify ALL provenance before any Docker mutation.
 for row in rows:
  tag=row['tag'].split(':')[1]
  token=json.loads(network('https://public.ecr.aws/token/?service=public.ecr.aws&scope=repository:docker/library/postgres:pull'))['token']
  hub=network('https://hub.docker.com/v2/repositories/library/postgres/tags/'+tag)
  index=network('https://public.ecr.aws/v2/docker/library/postgres/manifests/'+row['indexDigest'],token)
  manifest=network('https://public.ecr.aws/v2/docker/library/postgres/manifests/'+row['manifestDigest'],token)
  validate(row,hub,index,manifest)
 for row in rows:
  current=run(['docker','image','inspect',row['tag']],False)
  if current is not None:
   inspect_ok(row,json.loads(current)[0]);continue
  previous=run(['docker','image','inspect',row['mirror']],False)
  if previous is not None:inspect_ok(row,json.loads(previous)[0])
  if previous is None:
   mutate(['docker','pull','--platform','linux/amd64',row['mirror']],row['mirror'],row,run,receipt)
  inspect_ok(row,json.loads(run(['docker','image','inspect',row['mirror']]))[0])
  if run(['docker','image','inspect',row['tag']],False) is not None:raise ValueError('Preserve concurrently created original tag')
  mutate(['docker','tag',row['mirror'],row['tag']],row['tag'],row,run,receipt)
  inspect_ok(row,json.loads(run(['docker','image','inspect',row['tag']]))[0])
def main():
 import os,sys
 cleanup_mode=len(sys.argv)>1 and sys.argv[1]=='cleanup'
 path=Path(os.environ['RUNNER_TEMP'])/'procurement-postgres-preload.json';deadline=time.monotonic()+(90 if cleanup_mode else 240)
 def run(args,required=True):
  remaining=deadline-time.monotonic()
  if remaining<=1:raise TimeoutError('Preload deadline expired')
  result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(20 if cleanup_mode else 90,remaining),check=False)
  if result.returncode:
   if not required and args[:3]==['docker','image','inspect']:
    # Only absence permits creating a tag. Connection/permission errors are failures.
    if b'No such image' in result.stderr:return None
   raise RuntimeError('Owned Docker command failed: '+args[1])
  return result.stdout
 if cleanup_mode:
  if not path.exists():return
  data=json.loads(path.read_bytes())
  cleanup(data,run,lambda:atomic_save(path,data))
  return
 if path.exists():raise ValueError('Fresh preload receipt required')
 from datetime import datetime,timedelta,timezone
 data={'createdTags':[],'owner':'ordinary-hosted-job','containersStarted':False,'deadlineSeconds':240,'cleanupDeadlineSeconds':90,'hostedRunId':os.environ.get('GITHUB_RUN_ID'),'hostedRunAttempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'hostedJob':os.environ.get('GITHUB_JOB'),'leaseExpiresUtc':(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),'leaseExpiryDoesNotProveDaemonSettlement':True,'settlementAuthority':'successful CLI completion or externally verified ephemeral runner destruction'}
 def save():atomic_save(path,data)
 save();receipt={'createdTags':data['createdTags'],'write':save}
 preserve_primary(lambda:preload(json.loads((ROOT/'image-pins.json').read_bytes()),run,fetch,receipt),save)
 save()
def atomic_save(path,data):
 import os
 temporary=path.with_suffix('.pending')
 identity=None
 primary=None
 try:
  with temporary.open('xb') as handle:
   identity=os.fstat(handle.fileno())
   handle.write((json.dumps(data,indent=2)+'\n').encode());handle.flush();os.fsync(handle.fileno())
  os.replace(temporary,path)
 except BaseException as error:
  primary=error;raise
 finally:
  try:
   if identity is not None and temporary.exists():
    actual=temporary.stat()
    if (actual.st_dev,actual.st_ino)==(identity.st_dev,identity.st_ino):temporary.unlink()
  except BaseException as error:
   if primary is None:raise
   primary.add_note('Secondary pending receipt cleanup failure: '+type(error).__name__)
if __name__=='__main__':main()
