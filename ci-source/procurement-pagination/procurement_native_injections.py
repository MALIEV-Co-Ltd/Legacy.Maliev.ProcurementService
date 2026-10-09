"""Nine actual xUnit injections in a disposable copy; never runs without original gate."""
import hashlib,json,os,re,shutil,datetime
from pathlib import Path
from procurement_pagination_hosted_guards import require, IntegrityError, observe_roster, associated_roster, common_test_args, settings, binary_hashes, trx
from procurement_fixture_attribution import receipts, CLASSES
CASE_METHODS={
 'constructor-second-role':'ConstructorSecondRole','supplier-start':'SupplierStart',
 'order-start-after-supplier':'OrderStartAfterSupplier','receipt-admission-write':'ReceiptAdmissionWrite',
 'receipt-start-write':'ReceiptStartWrite','receipt-disposal-write':'ReceiptDisposalWrite',
 'disposal-timeout':'DisposalTimeout','concurrent-append-read':'ConcurrentAppendRead','short-serial-fixtures':'ShortSerialFixtures',
}
CLASS='Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementFiniteFailureInjectionTests'
KEYS={'sequence','case','kind','id','role','fixture','testClass','parentRun'}

def observe_controls(driver,case,directory,receipt_directory):
    directory=Path(directory)
    require(directory.is_dir() and not directory.is_symlink(),'Owned controls directory required')
    files=sorted(directory.iterdir())
    require(len(files)<=192,'Control file quota exceeded')
    for file in files:
        require(not file.is_symlink() and re.fullmatch(r'\d{4}\.json(?:\.ack|\.tmp)?',file.name),'Unreviewed control file')
        if file.suffix=='.tmp' and not file.exists():continue  # Atomic publish may move the temporary file during inventory.
        require(file.is_file(),'Control entry is not a regular file')
    events=driver.receipt.setdefault('injectionEvents',{})
    started=driver.receipt.setdefault('injectionStartedIds',{})
    rows=[f for f in files if f.suffix=='.json']
    require(len(rows)<=64,'Control event count exceeded')
    for file in rows:
        sequence=int(file.stem)
        require(1<=sequence<=64 and file.name==f'{sequence:04}.json' and file.is_file() and not file.is_symlink() and file.stat().st_size<=2048,'Control sequence/size/type differs')
        raw=file.read_bytes();require(len(raw)<=2048,'Control grew beyond bound')
        row=json.loads(raw)
        require(type(row) is dict and set(row)==KEYS and row['case']==case and row['parentRun']==driver.run and type(row['sequence']) is int and row['sequence']==sequence,'Control identity/schema differs')
        require(row['kind'] in ('health','absence','truncated-read','complete-read','case-complete'),'Control kind differs')
        if file.name in events:
            require(events[file.name]['row']==row,'Control event mutated');continue
        kind=row['kind']
        if kind=='health':
            require(re.fullmatch('[0-9a-f]{64}',row['id']) and re.fullmatch('[0-9a-f]{32}',row['fixture']) and row['testClass'] in CLASSES and row['role'] in ('Supplier','PurchaseOrder'),'Exact health identity required')
            require(row['id'] not in started,'Container ID reused')
            value,pg=driver.inspect(row['id'])
            labels=pg['labels']
            require(value['State']['Running'],'Started role not running')
            require(labels.get('maliev.codex.fixture-instance')==row['fixture'] and labels.get('maliev.codex.test-class')==row['testClass'] and labels.get('maliev.codex.database-role')==row['role'] and labels.get('maliev.codex.phase')=='candidate','Independent health labels differ')
            require(driver.receipt['postgres'].get(row['id'],{}).get('serverVersionNum',0) in range(180000,190000),'Independent PG18 health missing')
            created=datetime.datetime.fromisoformat(value['Created'].replace('Z','+00:00'))
            begin=datetime.datetime.fromisoformat(driver.receipt['injectionStartUtc'])
            require(begin<=created<=datetime.datetime.now(datetime.timezone.utc),'Stale container creation')
            started[row['id']]=row
        elif kind=='absence':
            require(row['id'] in started and row['role']==started[row['id']]['role'],'Absence ID/role not independently observed')
            require(row['id'] not in set(driver.docker('ps','-aq','--no-trunc').split()),'Exact role still exists')
        elif kind=='truncated-read':
            require(case=='concurrent-append-read','Unreviewed partial-read control')
            try:receipts(receipt_directory,driver.run,'candidate')
            except IntegrityError as exc:require(str(exc)=='Truncated receipt','Wrong receipt rejection')
            else:raise IntegrityError('Partial actual C# append was silently accepted')
        elif kind=='complete-read':
            require(case=='concurrent-append-read' and receipts(receipt_directory,driver.run,'candidate'),'Completed actual C# append missing')
        else:
            require(row['id']==row['role']==row['fixture']==row['testClass']=='','Case completion contains unexpected identity')
            require(not driver.owned_containers(),'Owned containers remain at case completion')
        events[file.name]={'row':row,'independentObservation':True}
        ack=file.with_name(file.name+'.ack')
        require(not ack.exists(),'Unowned/replayed acknowledgement')
        with ack.open('xb') as stream:stream.write(b'approved');stream.flush();os.fsync(stream.fileno())
        driver.save()

def final_controls(driver,case):
    events=list(driver.receipt.get('injectionEvents',{}).values())
    require(events and sum(e['row']['kind']=='case-complete' for e in events)==1,'Actual C# completion absent')
    require({e['row']['sequence'] for e in events}==set(range(1,len(events)+1)),'Missing terminal control sequence')
    starts=driver.receipt.get('injectionStartedIds',{})
    expected={'constructor-second-role':0,'supplier-start':0,'order-start-after-supplier':1,'receipt-admission-write':0,'receipt-start-write':1,'receipt-disposal-write':4,'disposal-timeout':2,'concurrent-append-read':2,'short-serial-fixtures':6}[case]
    require(len(starts)==expected,'Actual started role count differs')
    absent={e['row']['id'] for e in events if e['row']['kind']=='absence'}
    require(set(starts)==absent,'Exact started role absence missing')
    live=set(driver.docker('ps','-aq','--no-trunc').split())
    require(not set(starts)&live and not driver.owned_containers(),'Final exact-ID absence missing')
    if case=='short-serial-fixtures':
        for name in CLASSES:
            pair=[row for row in starts.values() if row['testClass']==name]
            require(len(pair)==2 and {r['role'] for r in pair}=={'Supplier','PurchaseOrder'} and len({r['fixture'] for r in pair})==1,'Serial class pair differs')
        require(len({r['fixture'] for r in starts.values()})==3,'Serial fixture UUID reused')
    if case=='concurrent-append-read':require({'truncated-read','complete-read'}<={e['row']['kind'] for e in events},'Actual concurrent append/read observations absent')
    return {'case':case,'startedIds':list(starts),'nativeBusinessAcceptance':False,'actualInjectionCompleted':True}

def install_copy(candidate,target):
    root=Path(__file__).resolve().parent
    manifest=root/'injection-overlay.json'
    require(hashlib.sha256(manifest.read_bytes()).hexdigest()==OVERLAY_SHA,'Injection overlay manifest drift')
    shutil.copytree(candidate,target,ignore=shutil.ignore_patterns('.git','bin','obj'))
    tests=target/'Legacy.Maliev.ProcurementService.Tests/Integration'
    for row in json.loads(manifest.read_bytes()):
        f=tests/row['name'];source=root/'injection-postimages'/row['name']
        require(not f.exists() if row['preimageSha256'] is None else f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest()==row['preimageSha256'],'Qualification-only preimage differs')
        require(hashlib.sha256(source.read_bytes()).hexdigest()==row['postimageSha256'],'Qualification-only postimage differs')
        f.write_bytes(source.read_bytes())

def run(driver,candidate):
    from procurement_pagination_hosted_driver import Driver, PROJECT
    target=driver.root/'injection-copy';install_copy(candidate,target)
    driver.command('injection-restore',['dotnet','restore',PROJECT,'--disable-parallel','--use-lock-file','-p:NuGetAudit=true','-p:NuGetAuditMode=all','-p:RestoreIgnoreFailedSources=false'],target,180)
    _,build=driver.command('injection-build',['dotnet','build',PROJECT,'-c','Release','--no-restore','-m:1','-nodeReuse:false','-p:UseSharedCompilation=false','-warnaserror'],target,240)
    require(re.search(r'\b0 Warning\(s\)',build) and re.search(r'\b0 Error\(s\)',build),'Actual C# injection build must be0W/E first')
    complete=observe_roster(driver,'injection-copy',target)
    injection_names=[CLASS+'.'+method for method in CASE_METHODS.values()]
    require(len(complete['names'])==419 and len(set(complete['names']))==419 and all(n in complete['names'] for n in injection_names),'Exact410 business plus9 separate injection discovery required')
    business={**complete,'names':[n for n in complete['names'] if n not in injection_names],'allUnfilteredDiscoveredNames':[n for n in complete['names'] if n not in injection_names]}
    associated_roster(business,full=True)
    for case,method in CASE_METHODS.items():
        root=driver.root/('injection-'+case);root.mkdir()
        child=Driver(root,driver.run);controls=root/'controls';controls.mkdir();receipts_dir=root/'candidate-fixture-receipts';receipts_dir.mkdir()
        child.receipt['injectionStartUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        original_probe=child.probe_postgres
        def probe():original_probe();observe_controls(child,case,controls,receipts_dir)
        child.probe_postgres=probe
        changes={'MALIEV_QUALIFICATION_CASE':case,'MALIEV_QUALIFICATION_CONTROLS':str(controls.resolve()),'MALIEV_TEST_RESOURCE_PHASE':'candidate','MALIEV_TEST_RESOURCE_RECEIPTS':str(receipts_dir.resolve())}
        previous={k:os.environ.get(k) for k in changes};os.environ.update(changes)
        try:
            results=root/'results';results.mkdir()
            selection={**complete,'names':[CLASS+'.'+method],'filter':'FullyQualifiedName='+CLASS+'.'+method}
            child.command(case,common_test_args(target,settings(root))+['--filter',selection['filter'],'--logger','trx;LogFileName=injection.trx','--results-directory',str(results)],target,240,monitor=True)
            probe();require(binary_hashes(target)==complete['binaryHashes'],'Injection compiled inputs changed')
            proof=trx(results,selection);require(proof['actualCases']==1 and proof['passed']==1,'Actual xUnit injection result differs')
            child.receipt['injectionProof']={**final_controls(child,case),'trx':proof};child.save()
            driver.receipt.setdefault('finiteCSharpInjections',{})[case]=child.receipt['injectionProof'];driver.save()
        finally:
            try:child.finish()
            finally:
                for key,value in previous.items():
                    if value is None:os.environ.pop(key,None)
                    else:os.environ[key]=value

OVERLAY_SHA='98df7b85bf8975799d94efb1b9caa6e88670c02c1eec7abb72d8ffe0dc1fffef'
