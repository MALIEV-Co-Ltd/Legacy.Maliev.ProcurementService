import hashlib,json,sys,tempfile,unittest,zipfile,stat
from pathlib import Path
from unittest.mock import patch
L=Path(__file__).resolve().parents[1];sys.path.insert(0,str(L))
import procurement_checkout_source as s
from procurement_pagination_hosted_guards import IntegrityError
class Fake:
    def __init__(self,root,rows,roots):
        self.root=root;root.mkdir();self.rows=rows;self.roots=roots;self.receipt={};self.calls=[];self.bad_head=False;self.dirty=False;self.poison=False;self.extra=False;self.link=False
    def save(self):pass
    def command(self,name,argv,cwd,timeout):
        self.calls.append((name,argv,timeout));row=self.rows[self.roots.index(Path(cwd))]
        if argv[1]=='rev-parse':return 0,('a'*40 if self.bad_head else row['commit'])+'\n'
        if argv[1]=='status':return 0,' M script.ps1' if self.dirty else ''
        if argv[1]!='archive':raise AssertionError('Only original bounded Git source operations allowed')
        target=Path(next(v.split('=',1)[1] for v in argv if v.startswith('--output=')))
        with zipfile.ZipFile(target,'x') as z:
            info=zipfile.ZipInfo('script.ps1')
            if self.link:info.external_attr=(stat.S_IFLNK|0o777)<<16
            z.writestr(info,b'X'+RAW[1:] if self.poison else RAW)
            if self.extra:z.writestr('foreign.txt',b'x')
        return 0,''
RAW=b"Write-Output 'source-fixture'\n"
class PartialWrite(OSError):pass
class CloseFailure(OSError):pass
class Held:
    def __init__(self,file,mode):self.file=file;self.mode=mode;self.close_calls=0
    @property
    def closed(self):return self.file.closed
    def fileno(self):return self.file.fileno()
    def write(self,raw):
        if self.mode=='write':self.file.write(raw[:3]);raise PartialWrite('partial attribute write')
        return self.file.write(raw)
    def close(self):
        self.close_calls+=1
        if self.mode=='close' and self.close_calls==1:raise CloseFailure('attribute close')
        return self.file.close()
class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);self.base=root/'base';self.deps=root/'deps';self.rows=[];self.roots=[]
        for name,commit in s.association.EXPECTED.items():
            target=self.base if name=='Legacy.Maliev.ProcurementService' else self.deps/name;target.mkdir(parents=True);(target/'.git/info').mkdir(parents=True)
            (target/'script.ps1').write_bytes(RAW.replace(b'\n',b'\r\n'));self.roots.append(target)
            self.rows.append({'repository':name,'commit':commit,'files':[{'path':'script.ps1','bytes':len(RAW),'sha256':hashlib.sha256(RAW).hexdigest(),'gitBlobOid':hashlib.sha1(b'blob '+str(len(RAW)).encode()+b'\0'+RAW).hexdigest()}]})
        self.driver=Fake(root/'receipt-root',self.rows,self.roots)
    def tearDown(self):self.temp.cleanup()
    def restore(self):
        with patch.object(s,'source_rows',return_value=self.rows),patch.object(s.association,'verify_context',return_value={'sourceOnly':True,'nativeExecuted':False}) as verify:
            proof=s.restore(self.driver,self.base,self.deps);verify.assert_called_once_with(self.base,self.deps);return proof
    def unchanged(self):
        for root in self.roots:self.assertEqual(RAW.replace(b'\n',b'\r\n'),(root/'script.ps1').read_bytes())
    def test_validated_raw_sources_restore_checkout_eol_only(self):
        proof=self.restore();self.assertEqual(4,proof['rawGitSourceFiles']);self.assertFalse(proof['nativeExecuted']);self.assertEqual(4,len(proof['restoredCheckoutPaths']))
        for root in self.roots:self.assertEqual(RAW,(root/'script.ps1').read_bytes())
        self.assertEqual(12,len(self.driver.calls));self.assertTrue(all(call[1][0]=='git' for call in self.driver.calls))
        self.assertTrue(all(not (root/'.git/info/attributes').exists() for root in self.roots))
    def test_wrong_source_head_preserves_checkout(self):
        self.driver.bad_head=True
        with self.assertRaises(IntegrityError):self.restore()
        self.unchanged()
    def test_dirty_source_preserved_before_writes(self):
        self.driver.dirty=True
        with self.assertRaises(IntegrityError):self.restore()
        self.unchanged()
    def test_wrong_raw_archive_hash_preserves_checkout(self):
        self.driver.poison=True
        with self.assertRaises(IntegrityError):self.restore()
        self.unchanged()
    def test_extra_archive_file_preserves_checkout(self):
        self.driver.extra=True
        with self.assertRaises(IntegrityError):self.restore()
        self.unchanged()
    def test_symlink_archive_entry_preserves_checkout(self):
        self.driver.link=True
        with self.assertRaises(IntegrityError):self.restore()
        self.unchanged()
    def test_untracked_checkout_inventory_preserved(self):
        (self.base/'foreign.txt').write_bytes(b'preserve')
        with self.assertRaises(IntegrityError):self.restore()
        self.assertEqual(b'preserve',(self.base/'foreign.txt').read_bytes());self.unchanged()
    def test_preexisting_local_attributes_preserved(self):
        file=self.base/'.git/info/attributes';file.write_bytes(b'preserve local metadata\n')
        with self.assertRaises(IntegrityError):self.restore()
        self.assertEqual(b'preserve local metadata\n',file.read_bytes());self.unchanged()
    def partial_open(self,mode):
        original=Path.open;attribute=self.base/'.git/info/attributes';held=[]
        def open_file(path,*args,**kwargs):
            file=original(path,*args,**kwargs)
            if path==attribute and args and args[0]=='xb':
                file=Held(file,mode);held.append(file)
            return file
        return open_file,held
    def partial_cleanup_proved(self):
        row=self.driver.receipt['temporaryGitAttributes'][0]
        self.assertTrue(row['identityCaptured']);self.assertTrue(row['handleClosed']);self.assertTrue(row['fileAbsent'])
        self.assertFalse(any(call[1][1]=='archive' for call in self.driver.calls));self.unchanged()
    def test_actual_partial_attribute_write_cleans_identity_before_archive(self):
        opened,held=self.partial_open('write')
        with patch.object(Path,'open',opened):
            with self.assertRaises(PartialWrite):self.restore()
        self.assertTrue(held[0].closed);self.partial_cleanup_proved()
    def test_actual_attribute_close_failure_retries_and_cleans_identity(self):
        opened,held=self.partial_open('close')
        with patch.object(Path,'open',opened):
            with self.assertRaises(CloseFailure):self.restore()
        self.assertEqual(2,held[0].close_calls);self.partial_cleanup_proved()
    def test_actual_first_fstat_failure_recaptures_held_identity_and_cleans(self):
        real=s.os.fstat;calls=[]
        def fstat(fd):
            calls.append(fd)
            if len(calls)==1:raise OSError('first held stat failure')
            return real(fd)
        with patch.object(s.os,'fstat',fstat):
            with self.assertRaisesRegex(OSError,'first held stat failure'):self.restore()
        self.assertEqual(2,len(calls));self.partial_cleanup_proved()
    def test_actual_uncertain_held_identity_preserves_file_and_primary(self):
        with patch.object(s.os,'fstat',side_effect=OSError('identity unavailable')):
            with self.assertRaisesRegex(OSError,'identity unavailable'):self.restore()
        row=self.driver.receipt['temporaryGitAttributes'][0]
        self.assertFalse(row['identityCaptured']);self.assertTrue(row['handleClosed']);self.assertFalse(row['fileAbsent'])
        self.assertTrue((self.base/'.git/info/attributes').exists());self.unchanged()
        self.assertFalse(any(call[1][1]=='archive' for call in self.driver.calls))
    def test_actual_replaced_attribute_identity_is_preserved(self):
        command=self.driver.command
        def replaced(name,argv,cwd,timeout):
            result=command(name,argv,cwd,timeout)
            if argv[1]=='archive':
                file=self.base/'.git/info/attributes';file.rename(file.with_name('original-owned-marker'))
                file.write_bytes(b'foreign replacement preserved\n')
            return result
        with patch.object(self.driver,'command',replaced):
            with self.assertRaisesRegex(RuntimeError,'cleanup incomplete'):self.restore()
        self.assertEqual(b'foreign replacement preserved\n',(self.base/'.git/info/attributes').read_bytes())
        self.assertFalse(self.driver.receipt['temporaryGitAttributes'][0]['fileAbsent']);self.unchanged()
    def test_proposed_original_dispatch_is_closed_without_inputs(self):
        workflow=(L.parents[1]/'.github/workflows/procurement-pagination-source-qualification.yml').read_text()
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.original_allocation_sha256 != '' && inputs.original_allocation_json != ''",workflow)
        self.assertLess(workflow.index('Admit exact original hosted allocation'),workflow.index('Restore and verify four exact Git source checkouts'))
        self.assertLess(workflow.index('Restore and verify four exact Git source checkouts'),workflow.index('Set up reviewed SDK'))
        for event,allocation,sha,expected in [('pull_request','x','x',False),('push','x','x',False),('workflow_dispatch','','x',False),('workflow_dispatch','x','',False),('workflow_dispatch','x','x',True)]:
            self.assertEqual(expected,event=='workflow_dispatch' and bool(allocation) and bool(sha))
if __name__=='__main__':unittest.main()
