"""Bounded phase receipts joined to independent existing-driver observations."""
import datetime, json, re
from pathlib import Path
from procurement_pagination_hosted_guards import IntegrityError, require
PREFIX='Legacy.Maliev.ProcurementService.Tests.Integration.'
CLASSES=tuple(PREFIX+n for n in ('ProcurementPaginationSourceTests','ProcurementPaginationWireContractTests','ProcurementIndependentContactTests'))
KEYS={'parentRun','phase','testClass','fixture','role','id','kind','sequence','utc','availableKiB'}
def require_event(row,run,phase,fixture,index):
    require(type(row) is dict and set(row)==KEYS,'Exact receipt keys required')
    require(row['parentRun']==run and row['phase']==phase,'Stale parent or phase')
    require(row['testClass'] in CLASSES and row['fixture']==fixture,'Crossed class or fixture')
    require(row['role'] in ('Supplier','PurchaseOrder'),'Invalid role')
    require(type(row['sequence']) is int and row['sequence']==index+1,'Receipt sequence differs')
    require(type(row['availableKiB']) is int,'Admission must be integer')
    require(row['kind'] in ('admission','start','dispose-start','dispose-return'),'Invalid event')
    require(row['id']=='' if row['kind']=='admission' else bool(re.fullmatch('[0-9a-f]{64}',row['id'])),'Exact container identity required')
    require(row['availableKiB']>=4194304 if row['kind']=='admission' else row['availableKiB']==0,'Admission floor differs')
    stamp=datetime.datetime.fromisoformat(row['utc'])
    require(stamp.utcoffset()==datetime.timedelta(0),'UTC receipt required')
    return stamp
def receipts(directory,run,phase,terminal=False):
    directory=Path(directory)
    require(directory.is_dir() and not directory.is_symlink(),'Owned phase receipt directory required')
    files=list(directory.iterdir())
    require(len(files)<=3,'Receipt file count exceeded')
    result=[]
    for file in files:
        require(file.is_file() and not file.is_symlink() and re.fullmatch(r'[0-9a-f]{32}\.jsonl',file.name),'Unreviewed receipt file')
        require(file.stat().st_size<=16384,'Oversize receipt')
        raw=file.read_bytes()
        require(len(raw)<=16384,'Receipt grew beyond bound')
        if not raw: require(not terminal,'Empty terminal receipt'); continue
        require(raw.endswith(b'\n'),'Truncated receipt')
        lines=raw.splitlines(); require(len(lines)<=8,'Event count exceeded')
        rows=[]; previous=None
        for i,line in enumerate(lines):
            require(len(line)<=2048,'Oversize event')
            row=json.loads(line)
            stamp=require_event(row,run,phase,file.stem,i)
            require(previous is None or stamp>=previous,'Receipt timestamps reversed');previous=stamp
            rows.append(row)
        require(len({row['testClass'] for row in rows})==1,'Class changed within fixture')
        expected=[('admission','Supplier'),('start','Supplier'),('admission','PurchaseOrder'),('start','PurchaseOrder'),('dispose-start','Supplier'),('dispose-return','Supplier'),('dispose-start','PurchaseOrder'),('dispose-return','PurchaseOrder')]
        require([(row['kind'],row['role']) for row in rows]==expected[:len(rows)],'Role lifecycle differs')
        require(not terminal or len(rows)==8,'Incomplete terminal lifecycle')
        for role in ('Supplier','PurchaseOrder'):
            ids={row['id'] for row in rows if row['role']==role and row['kind']!='admission'}
            require(len(ids)<=1,'Disposal ID differs from started role')
        result.extend(rows)
    return result
def observe(driver,phase,directory):
    rows=receipts(directory,driver.run,phase)
    observed=driver.receipt.setdefault('fixtureInspections',{})
    for row in rows:
        if row['kind']!='start' or row['id'] in observed: continue
        pg=driver.receipt['postgres'].get(row['id'])
        if not pg or not pg.get('serverVersionNum'): continue
        labels=pg['labels']
        created=datetime.datetime.fromisoformat(pg['createdUtc'].replace('Z','+00:00'))
        started=datetime.datetime.fromisoformat(driver.receipt['fixturePhaseStarts'][phase])
        event=datetime.datetime.fromisoformat(row['utc'])
        require(started<=created<=event<=datetime.datetime.now(datetime.timezone.utc),'Stale creation or future start receipt')
        require(labels.get('maliev.codex.fixture-instance')==row['fixture'] and labels.get('maliev.codex.test-class')==row['testClass'] and labels.get('maliev.codex.database-role')==row['role'] and labels.get('maliev.codex.phase')==phase,'Live labels differ from receipt')
        require(labels.get('maliev.codex.parent-run')==driver.run,'Inspection parent differs')
        # Existing Driver.inspect enforces owner, caps, ports, mounts and persistence.
        observed[row['id']]={**row,'createdUtc':pg['createdUtc'],'serverVersionNum':pg['serverVersionNum'],'independentInspect':True}
    driver.save()
def prove(driver,phase,directory,full=False):
    rows=receipts(directory,driver.run,phase,terminal=True)
    starts=[r for r in rows if r['kind']=='start']
    classes=CLASSES if phase!='baseline' else CLASSES[:1]
    require(len(starts)==2*len(classes),'Exact class pairs required')
    require(set(r['testClass'] for r in starts)==set(classes),'Missing or foreign class')
    require(len({r['id'] for r in starts})==len(starts),'Reused container ID')
    require(len({r['fixture'] for r in starts})==len(classes),'Reused fixture UUID')
    for name in classes:
        pair=[r for r in starts if r['testClass']==name]
        require(len(pair)==2 and {r['role'] for r in pair}=={'Supplier','PurchaseOrder'} and len({r['fixture'] for r in pair})==1,'Crossed class pair')
    # Unfiltered read-only inventory also detects an ID whose owner labels changed.
    live=set(driver.docker('ps','-aq','--no-trunc').split())
    for row in starts:
        observation=driver.receipt.get('fixtureInspections',{}).get(row['id'])
        require(observation and observation.get('independentInspect') is True,'Missed independent health observation')
        require(all(observation[k]==row[k] for k in ('parentRun','phase','testClass','fixture','role','id')),'Inspection identity mismatch')
        require(180000<=observation['serverVersionNum']<190000,'Missed PG18 health')
        begin=datetime.datetime.fromisoformat(driver.receipt['fixturePhaseStarts'][phase])
        require(all(begin<=datetime.datetime.fromisoformat(r['utc'])<=datetime.datetime.now(datetime.timezone.utc) for r in rows),'Stale lifecycle timestamp')
        require(row['id'] not in live,'Owned role still present')
    require(driver.receipt.get('cleanup',{}).get('ownedContainersAbsent') is True and not driver.receipt['cleanup'].get('failures'),'Final cleanup absence missing')
    return {'classAttributionQualified':True,'nativeAccepted':False,'phase':phase,'pairs':len(classes),'containerIds':[r['id'] for r in starts]}

def install(tests,phase):
    import hashlib
    root=Path(__file__).resolve().parent
    manifest=root/'attribution-overlay.json'
    require(hashlib.sha256(manifest.read_bytes()).hexdigest()=='2be9aa4fc4b4bd2acf62d734fdac8bbe068ab2befede174d65865d8fa049e243','Attribution manifest drift')
    for row in json.loads(manifest.read_bytes()):
        if phase=='baseline' and row['name'] in ('ProcurementPaginationWireContractTests.cs','ProcurementIndependentContactTests.cs'): continue
        target=Path(tests)/'Integration'/row['name']
        source=root/'attribution-postimages'/row['name']
        require(hashlib.sha256(source.read_bytes()).hexdigest()==row['postimageSha256'],'Attribution postimage drift')
        require(not target.exists() if row['preimageSha256'] is None else target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==row['preimageSha256'],'Attribution overlay preimage drift')
        target.write_bytes(source.read_bytes())
