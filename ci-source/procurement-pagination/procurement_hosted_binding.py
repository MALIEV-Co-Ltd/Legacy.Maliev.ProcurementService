"""Finite original-route qualification entry; never claims native acceptance."""
import hashlib,json,os,re,uuid
from datetime import datetime,timezone
from pathlib import Path
from procurement_pagination_hosted_guards import require

# The coordinator must supply the reviewed byte pin to the assigned hosted run.
# It is external to the source commit, preventing a commit/allocation hash cycle.
REPOSITORY = 'MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService'
WORKFLOW = '.github/workflows/procurement-pagination-source-qualification.yml'
V3_SEAL = '2c0938b9406553755f820bb1f85f5bf55de73d9e7d64b824a6264c1978abb2ce'
V3_MANIFEST = '30c41380a1079d979376aaf9eff61594092eae0d13421fb44823ff5432eb211e'
KEYS = {'owner','allocationId','repository','workflow','transportCommit','job','issuedUtc','expiresUtc','floorKiB','jobTimeoutMinutes','v3SealSha256','v3ManifestSha256','purpose'}

def admit(path,expected_sha=None,env=None,now=None,memory=None):
    env=os.environ if env is None else env
    now=datetime.now(timezone.utc) if now is None else now
    require(isinstance(expected_sha,str) and re.fullmatch('[0-9a-f]{64}',expected_sha),'Fresh reviewed original allocation byte pin missing')
    target=Path(path)
    require(target.is_file() and not target.is_symlink() and target.stat().st_size<=8192,'Finite allocation file missing or aliased')
    raw=target.read_bytes()
    require(len(raw)<=8192 and hashlib.sha256(raw).hexdigest()==expected_sha,'Allocation byte identity differs')
    a=json.loads(raw)
    require(type(a) is dict and set(a)==KEYS,'Exact original allocation tuple required')
    require(a['owner']=='01a1009c-aa47-72d2-9914-3a0784a67c0e' and a['purpose']=='original-procurement-qualification','Wrong allocation owner or route')
    require(a['repository']==REPOSITORY and a['workflow']==WORKFLOW and a['job']=='validate','Wrong hosted target')
    require(a['v3SealSha256']==V3_SEAL and a['v3ManifestSha256']==V3_MANIFEST,'Reviewed V3 byte pins differ')
    require(type(a['floorKiB']) is int and a['floorKiB']==4194304 and type(a['jobTimeoutMinutes']) is int and a['jobTimeoutMinutes']==60,'Original guard or caps differ')
    require(re.fullmatch('[0-9a-f]{40}',a['transportCommit']) and str(uuid.UUID(a['allocationId']))==a['allocationId'],'Exact transport commit/allocation identity required')
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_OS')=='Linux' and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch','Original hosted Linux dispatch required')
    expected={'GITHUB_REPOSITORY':a['repository'],'GITHUB_SHA':a['transportCommit'],'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':a['job'],'MALIEV_TEST_RESOURCE_RUN_ID':a['allocationId']}
    require(all(type(value) is str and env.get(key)==value for key,value in expected.items()),'Hosted execution tuple differs')
    require(re.fullmatch('[1-9][0-9]*',env.get('GITHUB_RUN_ID','')),'Finite run identity required')
    require(env.get('GITHUB_WORKFLOW_SHA')==a['transportCommit'] and env.get('GITHUB_WORKFLOW_REF','').startswith(REPOSITORY+'/'+WORKFLOW+'@'),'Hosted caller source differs')
    issued=datetime.fromisoformat(a['issuedUtc']);expiry=datetime.fromisoformat(a['expiresUtc'])
    require(issued.utcoffset()==expiry.utcoffset()==timezone.utc.utcoffset(now),'UTC allocation required')
    require(issued<=now<expiry and 0<(expiry-issued).total_seconds()<=3600,'Original allocation expired or widened')
    if memory is None:
        match=re.search(r'^MemAvailable:\s+(\d+) kB$',Path('/proc/meminfo').read_text(),re.M)
        require(match is not None,'Fresh hosted capacity unavailable')
        memory=int(match.group(1))
    require(type(memory) is int and memory>=4194304,'Fresh fixed 4GiB floor unavailable')
    return {'qualificationExecutionAllowed':True,'nativeAccepted':False,'allocationId':a['allocationId'],'expiresUtc':a['expiresUtc'],'transportCommit':a['transportCommit'],'runId':env['GITHUB_RUN_ID'],'runAttempt':'1','remainingSeconds':(expiry-now).total_seconds(),'observedAvailableKiB':memory}

def remaining(binding):
    expiry=datetime.fromisoformat(binding['expiresUtc'])
    seconds=(expiry-datetime.now(timezone.utc)).total_seconds()
    require(seconds>0,'Original hosted allocation expired')
    return seconds
