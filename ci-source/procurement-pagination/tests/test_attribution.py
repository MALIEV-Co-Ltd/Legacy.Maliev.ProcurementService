import copy,datetime,hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import procurement_fixture_attribution as a
import procurement_pagination_hosted_driver as d
ROOT=Path(__file__).resolve().parents[1]
RUN='11111111-1111-4111-8111-111111111111'
NOW=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=30)
def time(offset): return (NOW+datetime.timedelta(seconds=offset)).isoformat()
class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.directory=self.root/'receipts';self.directory.mkdir()
        self.driver=d.Driver(self.root,RUN)
        self.driver.receipt['fixturePhaseStarts']={'candidate':time(-10),'baseline':time(-10)}
        self.live={};self.rows=[]
        for index,name in enumerate(a.CLASSES):
            fixture=f'{index+1:032x}';ids=[f'{index*2+1:064x}',f'{index*2+2:064x}']
            lifecycle=[('admission','Supplier',''),('start','Supplier',ids[0]),('admission','PurchaseOrder',''),('start','PurchaseOrder',ids[1]),('dispose-start','Supplier',ids[0]),('dispose-return','Supplier',ids[0]),('dispose-start','PurchaseOrder',ids[1]),('dispose-return','PurchaseOrder',ids[1])]
            rows=[dict(parentRun=RUN,phase='candidate',testClass=name,fixture=fixture,role=role,id=cid,kind=kind,sequence=i+1,utc=time(i),availableKiB=4194304 if kind=='admission' else 0) for i,(kind,role,cid) in enumerate(lifecycle)]
            self.rows.append(rows)
        self.write()
        self.driver.docker=self.docker
        self.driver.quick=lambda *args,**kwargs:(0,b'180001\n')
    def tearDown(self): self.tmp.cleanup()
    def write(self):
        for f in self.directory.iterdir(): f.unlink()
        for rows in self.rows:
            (self.directory/(rows[0]['fixture']+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    def docker(self,*args):
        if args[0]=='ps': return '\n'.join(self.live)
        if args[0]=='inspect': return json.dumps([self.live[args[1]]])
        raise ValueError('Unexpected modeled Docker operation')
    def container(self,row):
        return dict(Id=row['id'],Created=time(-1),State={'Running':True},Config={'Image':'postgres:18.1-bookworm','Labels':{'maliev.codex.owner':'commerce-procurement-qualification-20261007','maliev.codex.parent-run':RUN,'maliev.codex.persistent-data':'false','maliev.codex.fixture-instance':row['fixture'],'maliev.codex.test-class':row['testClass'],'maliev.codex.database-role':row['role'],'maliev.codex.phase':'candidate'}},HostConfig={'Memory':1073741824,'MemorySwap':1073741824,'NanoCpus':750000000,'Tmpfs':{'/var/lib/postgresql':'rw,size=512m'}},NetworkSettings={'Ports':{'5432/tcp':[{'HostIp':'127.0.0.1'}]}},Mounts=[])
    def inspect_serial(self):
        self.driver.fixture_phase='candidate';self.driver.fixture_directory=self.directory
        for rows in self.rows:
            self.live={row['id']:self.container(row) for row in rows if row['kind']=='start'}
            self.driver.probe_postgres()
        self.live={};self.driver.receipt['cleanup']={'ownedContainersAbsent':True,'failures':[]}
    def proof(self):return a.prove(self.driver,'candidate',self.directory)
    def test_serial_noncoexisting_pairs_actual_monitor(self):
        self.inspect_serial();self.assertEqual(3,self.proof()['pairs'])
    def test_crossed_class(self):
        self.rows[0][1]['testClass']=a.CLASSES[1];self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_crossed_uuid(self):
        self.rows[0][1]['fixture']='f'*32;self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_swapped_roles(self):
        self.rows[0][1]['role']='PurchaseOrder';self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_reused_container_ids(self):
        for row in self.rows[1]:
            if row['id']==f'{3:064x}':row['id']=f'{1:064x}'
        self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial();self.proof()
    def test_missing_health(self):
        self.inspect_serial();self.driver.receipt['fixtureInspections'].pop(f'{1:064x}')
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_unrelated_healthy_pair(self):
        self.driver.receipt['postgres']={'f'*64:{'serverVersionNum':180001}}
        self.driver.receipt['cleanup']={'ownedContainersAbsent':True,'failures':[]}
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_missing_final_absence(self):
        self.inspect_serial();self.driver.receipt['cleanup']['ownedContainersAbsent']=False
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_still_present_id_even_after_label_change(self):
        self.inspect_serial();self.live={f'{1:064x}':{}}
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_missing_disposal(self):
        self.inspect_serial();self.rows[0]=self.rows[0][:-1];self.write()
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_disposal_id_differs(self):
        self.rows[0][-3]['id']='f'*64;self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_receipt_environment_survives_actual_runner(self):
        env=d.runner_environment({'MALIEV_TEST_RESOURCE_PHASE':'candidate','MALIEV_TEST_RESOURCE_RECEIPTS':'/owned/receipts','UNREVIEWED_SECRET':'redacted'})
        self.assertEqual('candidate',env['MALIEV_TEST_RESOURCE_PHASE'])
        self.assertEqual('/owned/receipts',env['MALIEV_TEST_RESOURCE_RECEIPTS'])
        self.assertNotIn('UNREVIEWED_SECRET',env)
    def test_stale_parent(self):
        self.rows[0][0]['parentRun']='other';self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_stale_phase(self):
        self.rows[0][0]['phase']='baseline';self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_stale_timestamp(self):
        self.rows[0][0]['utc']=time(-100);self.write();self.inspect_serial()
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_old_container_creation(self):
        self.driver.fixture_phase='candidate';self.driver.fixture_directory=self.directory
        row=self.rows[0][1];self.live={row['id']:self.container(row)};self.live[row['id']]['Created']=time(-100)
        with self.assertRaises(a.IntegrityError):self.driver.probe_postgres()
    def test_truncated_receipt(self):
        f=next(self.directory.iterdir());f.write_bytes(f.read_bytes()[:-1])
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_oversize_receipt(self):
        next(self.directory.iterdir()).write_bytes(b'x'*16385)
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_bad_admission_floor(self):
        self.rows[0][0]['availableKiB']=4194303;self.write()
        with self.assertRaises(a.IntegrityError):self.inspect_serial()
    def test_label_role_differs(self):
        self.driver.fixture_phase='candidate';self.driver.fixture_directory=self.directory
        row=self.rows[0][1];self.live={row['id']:self.container(row)};self.live[row['id']]['Config']['Labels']['maliev.codex.database-role']='PurchaseOrder'
        with self.assertRaises(a.IntegrityError):self.driver.probe_postgres()
    def test_empty_receipt_terminal(self):
        self.inspect_serial();next(self.directory.iterdir()).write_bytes(b'')
        with self.assertRaises(a.IntegrityError):self.proof()
    def test_phase_directory_unique_actual_entry(self):
        with patch.dict(os.environ,{},clear=False):
            self.driver.begin_fixture_phase('baseline')
            with self.assertRaises(FileExistsError):self.driver.begin_fixture_phase('baseline')
    def test_baseline_exact_one_pair(self):
        self.rows=self.rows[:1]
        for row in self.rows[0]:row['phase']='baseline'
        self.write();self.driver.fixture_phase='baseline';self.driver.fixture_directory=self.directory
        self.live={r['id']:self.container(r) for r in self.rows[0] if r['kind']=='start'}
        for value in self.live.values():value['Config']['Labels']['maliev.codex.phase']='baseline'
        self.driver.probe_postgres();self.live={};self.driver.receipt['cleanup']={'ownedContainersAbsent':True,'failures':[]}
        self.assertEqual(1,a.prove(self.driver,'baseline',self.directory)['pairs'])
    def test_fixture_cleanup_source_boundaries(self):
        text=(ROOT/'attribution-postimages/ProcurementRuntimeParityTests.cs').read_text(encoding='utf-8')
        self.assertIn('public ProcurementRuntimeFixture() : this(null)',text)
        self.assertIn('base(typeof(TTestClass))',text)
        self.assertIn('DisposeAsync(acquired).GetAwaiter().GetResult()',text)
        self.assertIn('var failures = new List<Exception> { original }',text)
        self.assertIn('}, DisposeAsync);',text)
        self.assertLess(text.index('await DisposeRoleAsync(supplier'),text.index('await DisposeRoleAsync(order'))
        body=text.split('private async Task DisposeRoleAsync',1)[1]
        self.assertLess(body.index('catch (Exception failure) { failures.Add(failure); }'),body.index('await OwnedProcurementTestContainers.DisposeAsync(container)'))
    def test_writer_bounds_and_nonsecret_schema(self):
        text=(ROOT/'attribution-postimages/ProcurementFixtureReceipt.cs').read_text(encoding='utf-8')
        for term in ('sequence >= 8','bytes.Length > 2048','> 16384','FileMode.CreateNew','FileMode.Append','stream.Flush(true)','available < 4194304'):self.assertIn(term,text)
        for term in ('GetConnectionString','Exception.Message','Password'):self.assertNotIn(term,text)
    def test_actual_finish_entry_proves_after_cleanup(self):
        self.inspect_serial();calls=[]
        self.driver.cleanup=lambda:calls.append('cleanup')
        self.driver.finish_fixture_phase()
        self.assertEqual(['cleanup'],calls)
        self.assertEqual(3,self.driver.receipt['fixtureQualification']['candidate']['pairs'])
    def overlay_tree(self,phase):
        tests=self.root/'Tests';integration=tests/'Integration';integration.mkdir(parents=True)
        with zipfile.ZipFile(ROOT/'source-packet.zip') as z:
            for n in z.namelist():
                if n.endswith('.cs') and '/Integration/' in n and (phase!='baseline' or n.endswith('ProcurementPaginationSourceTests.cs')):
                    (integration/Path(n).name).write_bytes(z.read(n))
        fixture=ROOT.parents[1]/'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs'
        (integration/fixture.name).write_bytes(fixture.read_text(encoding='utf-8-sig').replace('new PostgreSqlBuilder(','OwnedProcurementTestContainers.Postgres(').encode('utf-8'))
        return tests
    def test_actual_candidate_overlay(self):
        tests=self.overlay_tree('candidate');a.install(tests,'candidate')
        for f in (ROOT/'attribution-postimages').glob('*.cs'):self.assertEqual(f.read_bytes(),(tests/'Integration'/f.name).read_bytes())
    def test_actual_baseline_overlay(self):
        tests=self.overlay_tree('baseline');a.install(tests,'baseline')
        self.assertFalse((tests/'Integration/ProcurementIndependentContactTests.cs').exists())
        self.assertIn('ProcurementRuntimeFixture<ProcurementPaginationSourceTests>',(tests/'Integration/ProcurementPaginationSourceTests.cs').read_text(encoding='utf-8'))
        source=(ROOT/'procurement_pagination_hosted_driver.py').read_text(encoding='utf-8')
        self.assertLess(source.index('install_fixture(tests, phase)'),source.index("if phase == 'baseline':\n            regression = dest"))
    def test_actual_overlay_rejects_foreign_preimage(self):
        tests=self.overlay_tree('candidate');(tests/'Integration/ProcurementPaginationSourceTests.cs').write_text('foreign')
        with self.assertRaises(a.IntegrityError):a.install(tests,'candidate')
if __name__=='__main__':unittest.main()
