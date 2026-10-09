import io,json,sys,tempfile,unittest
from pathlib import Path as RealPath
from unittest.mock import patch
ROOT=RealPath(__file__).resolve().parents[1]
MODE=sys.argv.pop() if sys.argv[-1] in ('old','fixed','expiry-old') else 'fixed'
SOURCE=ROOT.parent/'procurement-finite-csharp-injections-source-v1-20261010' if MODE=='old' else ROOT.parent/'procurement-finite-csharp-injections-source-v2-command-cleanup-20261010' if MODE=='expiry-old' else ROOT
sys.path.insert(0,str(SOURCE))
import procurement_pagination_hosted_driver as d
class Primary(RuntimeError):pass
class Secondary(RuntimeError):pass
class Stream(io.BytesIO):
    def __init__(self,world):super().__init__();self.world=world;self.fail_close=False;self.closed_under_writer=False
    def close(self):
        self.closed_under_writer=any(v['session']==77777 and v['state']!='Z' for v in self.world.values())
        if self.fail_close:self.fail_close=False;raise Secondary('stream close')
        super().close()
class Process:
    pid=77777
    def __init__(self,world):self.world=world;self.stdout=Stream(world);self.returncode=None;self.waits=[];self.wait_calls=[];self.terminated=0;self.killed=0;self.stubborn=False
    def poll(self):return self.returncode
    def terminate(self):self.terminated+=1
    def kill(self):self.killed+=1
    def wait(self,timeout):
        self.wait_calls.append(timeout)
        value=self.waits.pop(0) if self.waits else 0
        if isinstance(value,BaseException):raise value
        if not self.stubborn:self.returncode=value;self.world.pop(self.pid,None)
        return value
class Selector:
    def __init__(self):self.register_error=None;self.body_error=None;self.close_error=None;self.closed=False
    def register(self,*args):
        if self.register_error:raise self.register_error
    def get_map(self):
        if self.body_error:raise self.body_error
        return {}
    def close(self):
        if self.close_error:error=self.close_error;self.close_error=None;raise error
        self.closed=True
class Node:
    def __init__(self,text,case):self.text=text;self.case=case;self.name=text.rsplit('/',1)[-1]
    def __truediv__(self,value):return Node(self.text+'/'+value,self.case)
    def iterdir(self):
        if self.case.inventory_error:raise self.case.inventory_error
        return [Node('/proc/'+str(pid),self.case) for pid in self.case.world]
    def read_text(self,*args,**kwargs):
        pid=int(self.text.split('/')[2])
        if self.case.birth_error and pid==77777:
            error=self.case.birth_error;self.case.birth_error=None;raise error
        value=self.case.world.get(pid)
        if value is None:raise FileNotFoundError(self.text)
        fields=[value['state'],'1','1',str(value['session'])]+['0']*15+[value['birth']]
        return str(pid)+' (owned) '+' '.join(fields)
    def exists(self):return int(self.text.split('/')[2]) in self.case.world
    def resolve(self,strict=False):
        if self.case.exe_error:raise self.case.exe_error
        return RealPath('/owned/command')
class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=RealPath(self.tmp.name);self.world={77777:{'session':77777,'birth':'100','state':'R'},6580:{'session':6580,'birth':'foreign','state':'R'}}
        self.proc=Process(self.world);self.sel=Selector();self.driver=d.Driver(self.root,'owned-run');self.signals=[];self.inventory_error=self.birth_error=self.exe_error=None
        self.stack=[]
        def path(value):return Node(str(value),self) if str(value).startswith('/proc') else RealPath(value)
        def kill(pid,sig):
            self.signals.append((pid,sig))
            if pid!=77777 and not self.world[pid].get('stubborn'):self.world.pop(pid,None)
        for patcher in [patch.object(d,'Path',side_effect=path),patch.object(d.subprocess,'Popen',return_value=self.proc),patch.object(d.selectors,'DefaultSelector',return_value=self.sel),patch.object(d.os,'kill',side_effect=kill),patch.object(d.time,'sleep'),patch.object(d.signal,'SIGKILL',9,create=True)]:patcher.start();self.stack.append(patcher)
    def tearDown(self):
        for patcher in reversed(self.stack):patcher.stop()
        if not self.proc.stdout.closed:self.proc.stdout.fail_close=False;self.world.clear();self.proc.stdout.close()
        self.tmp.cleanup()
    def command(self):return self.driver.command('modeled-owned', ['owned-command'],self.root,3)
    def assert_settled(self):
        self.assertTrue(self.proc.stdout.closed);self.assertTrue(self.sel.closed);self.assertFalse(self.proc.stdout.closed_under_writer)
        row=self.driver.receipt['processes'][-1];self.assertTrue(row['exited']);self.assertTrue(row['handleClosed'])
        self.assertTrue(6580 in self.world);self.assertFalse(any(pid==6580 for pid,_ in self.signals))
    def test_primary_survives_secondary_wait_and_handles_settle(self):
        primary=Primary('original');self.proc.waits=[primary,Secondary('cleanup wait'),0]
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Primary vanished')
        self.assert_settled()
    def test_primary_survives_secondary_live_member_cleanup(self):
        primary=Primary('original');self.sel.body_error=primary;self.world[77778]={'session':77777,'birth':'101','state':'R','stubborn':True}
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Primary vanished')
        self.assertFalse(self.proc.stdout.closed);self.assertTrue(self.sel.closed)
        self.assertTrue(self.driver.receipt['processes'][-1]['outerCustodyRequired'])
    def test_partial_birth_capture_still_settles_retained_child(self):
        primary=Primary('birth');self.birth_error=primary
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Partial startup failure vanished')
        self.assertTrue(self.proc.stdout.closed);self.assertTrue(self.driver.receipt['processes'][-1]['exited'])
        self.assertGreater(self.proc.terminated,0)
    def test_partial_executable_capture_still_settles_child(self):
        primary=Primary('executable');self.exe_error=primary
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Partial startup failure vanished')
        self.assertTrue(self.proc.stdout.closed)
    def test_partial_selector_registration_closes_independently(self):
        primary=Primary('register');self.sel.register_error=primary
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Partial startup failure vanished')
        self.assert_settled()
    def test_popen_failure_keeps_original_without_resource(self):
        primary=Primary('popen')
        with patch.object(d.subprocess,'Popen',side_effect=primary):
            try:self.command()
            except BaseException as result:self.assertIs(primary,result)
            else:self.fail('Spawn failure vanished')
        row=self.driver.receipt['processes'][-1];self.assertFalse(row['started']);self.assertTrue(row['handleClosed'])
    def test_primary_save_failure_does_not_skip_settlement(self):
        primary=Primary('receipt')
        with patch.object(self.driver,'save',side_effect=primary):
            try:self.command()
            except BaseException as result:self.assertIs(primary,result)
            else:self.fail('Primary vanished')
        self.assertTrue(self.proc.stdout.closed)
    def test_selector_close_failure_does_not_skip_pipe_close(self):
        self.sel.close_error=Secondary('selector')
        with self.assertRaises(RuntimeError):self.command()
        self.assertTrue(self.proc.stdout.closed)
        self.assertFalse(self.driver.receipt['processes'][-1]['handleClosed'])
    def test_unproved_live_parent_never_closes_pipe(self):
        primary=Primary('body');self.sel.body_error=primary;self.proc.stubborn=True;self.proc.waits=[Secondary('wait1'),Secondary('wait2')]
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Primary vanished')
        self.assertFalse(self.proc.stdout.closed);self.assertTrue(self.sel.closed)
        self.assertFalse(self.driver.receipt['processes'][-1]['exited'])
    def test_inventory_failure_never_closes_unknown_writer(self):
        primary=Primary('body');self.sel.body_error=primary;self.inventory_error=Secondary('inventory')
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Primary vanished')
        self.assertFalse(self.proc.stdout.closed);self.assertTrue(self.sel.closed)
    def test_existing_outer_finish_reobserves_then_closes_pipe(self):
        primary=Primary('body');self.sel.body_error=primary;self.world[77778]={'session':77777,'birth':'101','state':'R','stubborn':True}
        try:self.command()
        except Primary:pass
        self.assertFalse(self.proc.stdout.closed)
        self.world.pop(77778)
        with patch.object(self.driver,'cleanup'):self.driver.finish()
        self.assertTrue(self.proc.stdout.closed);self.assertFalse(self.driver._pending_commands)
    def test_cleanup_secondary_without_primary_is_reported(self):
        self.proc.waits=[0,Secondary('wait'),0]
        with self.assertRaises(RuntimeError):self.command()
        self.assert_settled()
    def test_signal_uses_exact_birth_and_preserves_foreign_pid(self):
        self.world[77778]={'session':77777,'birth':'101','state':'R'}
        self.command();self.assert_settled()
        self.assertIn((77778,d.signal.SIGTERM),self.signals)
    def test_stdout_close_failure_is_retained_and_outer_retries(self):
        self.proc.stdout.fail_close=True
        with self.assertRaises(RuntimeError):self.command()
        self.assertFalse(self.proc.stdout.closed)
        with patch.object(self.driver,'cleanup'):self.driver.finish()
        self.assertTrue(self.proc.stdout.closed)
    def test_partial_selector_creation_settles_pipe(self):
        primary=Primary('selector constructor')
        with patch.object(d.selectors,'DefaultSelector',side_effect=primary):
            try:self.command()
            except BaseException as result:self.assertIs(primary,result)
            else:self.fail('Primary vanished')
        self.assertTrue(self.proc.stdout.closed)
    def test_exact_birth_change_never_signals_reused_member(self):
        self.world[77778]={'session':77777,'birth':'101','state':'R'}
        original=d.Driver.birth
        def birth(pid):
            if pid==77778:self.world[77778]['birth']='102'
            return original(pid)
        with patch.object(self.driver,'birth',side_effect=birth),self.assertRaises(RuntimeError):self.command()
        self.assertFalse(any(pid==77778 for pid,_ in self.signals));self.assertFalse(self.proc.stdout.closed)
        self.assertTrue(self.driver.receipt['processes'][-1]['outerCustodyRequired'])
    def test_primary_note_failure_cannot_replace_primary(self):
        class BadNote(Primary):
            def add_note(self,*args):raise Secondary('annotation')
        primary=BadNote('original');self.proc.waits=[primary,Secondary('wait'),0]
        try:self.command()
        except BaseException as result:self.assertIs(primary,result)
        else:self.fail('Primary vanished')
        self.assert_settled()
    def test_outer_custody_no_primary_reports_unresolved_exit(self):
        primary=Primary('body');self.sel.body_error=primary;self.proc.stubborn=True;self.proc.waits=[Secondary('wait1'),Secondary('wait2')]
        try:self.command()
        except Primary:pass
        with patch.object(self.driver,'cleanup'),self.assertRaises(RuntimeError):self.driver.finish()
        self.assertFalse(self.proc.stdout.closed)
        self.assertIn('outerCustodyExpiresUtc',self.driver.receipt['processes'][-1])
    def test_original_absolute_deadline_bounds_near_expiry_settlement(self):
        clock=[100.0];primary=Primary('body');self.proc.stubborn=True;self.proc.waits=[Secondary('wait1'),Secondary('wait2')]
        original=self.proc.wait
        def wait(timeout):clock[0]+=timeout;return original(timeout)
        def body():clock[0]=116.0;raise primary
        with patch.object(d.time,'monotonic',side_effect=lambda:clock[0]),patch.object(d.time,'sleep',side_effect=lambda value:clock.__setitem__(0,clock[0]+value)),patch.object(self.proc,'wait',side_effect=wait),patch.object(self.sel,'get_map',side_effect=body):
            try:self.command()
            except BaseException as result:self.assertIs(primary,result)
            self.assertLessEqual(clock[0],118.0,'Cleanup exceeded original start+timeout+15 boundary')
    def test_outer_finish_cannot_restart_expired_wait_budget(self):
        clock=[100.0];primary=Primary('body');self.sel.body_error=primary;self.proc.stubborn=True;self.proc.waits=[Secondary('wait')]*8
        original=self.proc.wait
        def wait(timeout):clock[0]+=timeout;return original(timeout)
        with patch.object(d.time,'monotonic',side_effect=lambda:clock[0]),patch.object(d.time,'sleep',side_effect=lambda value:clock.__setitem__(0,clock[0]+value)),patch.object(self.proc,'wait',side_effect=wait):
            try:self.command()
            except Primary:pass
            count=len(self.proc.wait_calls);clock[0]=119.0
            with patch.object(self.driver,'cleanup'),self.assertRaises(RuntimeError):self.driver.finish()
            self.assertEqual(count,len(self.proc.wait_calls),'Outer finish renewed original expired command wait budget')
            self.assertFalse(self.proc.stdout.closed)
if __name__=='__main__':unittest.main()
