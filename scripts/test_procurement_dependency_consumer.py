"""Pure dependency admission controls; mocked Git metadata is not hosted HEAD proof."""
import ast
import copy
import importlib.util
import json
import os
import datetime
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import procurement_dependency_consumer as d

REAL=Path(__file__).resolve().parents[1]
LANES=dict([('file-metadata','procurement-file-metadata-binding-contract.json'),('supplier-identity','procurement-supplier-identity-contract.json'),
 ('metadata-identity','procurement-metadata-identity-contract.json'),('metadata-ignored-audits','procurement-metadata-ignored-audits-contract.json'),
 ('header-ignored-fields','procurement-header-ignored-fields-contract.json'),('supplier-ignored-audits','procurement-supplier-ignored-audits-contract.json')])

class DependencyConsumerControls(unittest.TestCase):
    def setUp(self):
        self.owner=tempfile.TemporaryDirectory(prefix='.procurement-dependency-control-',dir=REAL.parent);self.addCleanup(self.owner.cleanup)
        (Path(self.owner.name)/'task-owner.json').write_text(json.dumps(dict(task='Procurement59-dependency-controls',process=d.process_identity(),createdUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),leaseSeconds=120,controlSha256=d.record(Path(__file__).read_bytes())['sha256'])))
        self.root=Path(self.owner.name)/'source'
        shutil.copytree(REAL,self.root,ignore=shutil.ignore_patterns('.git','.dependencies','__pycache__','bin','obj'))
        self.git_rows={}
        for name in d.ORIGINAL:
            raw=d.transformed(self.root,name) if name in d.TRANSFORMS else d.read(self.root,name)
            self.git_rows[name]='100644 blob '+d.canonical_blob(name,raw)
        for name in {d.MODULE,d.CONTROLS,d.PROFILE}|{r['archive'] for r in d.ARCHIVES.values()}:
            self.git_rows[name]='100644 blob '+d.blob_bytes(d.read(self.root,name))

    def git(self,root,*args):
        self.assertEqual(self.root,root);self.assertEqual(('ls-tree','-r','-z','HEAD'),args)
        return b''.join((v+'\t'+p+'\0').encode() for p,v in sorted(self.git_rows.items()))

    def check(self):return d.authenticate_dependency(self.root,self.git)

    def module(self,lane):
        spec=importlib.util.spec_from_file_location('_dependency_'+lane,self.root/f'scripts/prepare-{lane}-baseline.py')
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

    def profile(self):return d.parse(d.read(self.root,d.PROFILE))
    def save(self,p):
        (self.root/d.PROFILE).write_bytes((json.dumps(p,indent=2)+'\n').encode())
        self.git_rows[d.PROFILE]='100644 blob '+d.blob_bytes(d.read(self.root,d.PROFILE))

    def reseal(self,path,raw):
        (self.root/path).write_bytes(raw);profile=self.profile()
        for row in profile['currentChanges']:
            if row['path']==path:row['current']=d.record(raw)
        for row in profile['additionalInputs']:
            if row['path']==path:row.update(d.record(raw))
        self.git_rows[path]='100644 blob '+d.blob_bytes(raw);self.save(profile)

    def test_exact_current_source_and_mock_metadata_admission(self):
        self.assertIs(False,self.check()['executionGranted'])
        self.assertEqual(20,len(d.TRANSFORMS));self.assertEqual(3,len(d.DEPENDENCIES))

    def test_all_six_actual_current_binding_layers(self):
        self.check()
        for lane,contract in LANES.items():
            with self.subTest(lane=lane):
                guard=self.module(lane);manifest=d.parse(d.read(self.root,'docs/'+contract))
                actual=lambda root,p:d.blob_bytes(d.read(root,p))
                guard.blob=actual
                if hasattr(guard,'require_runtime_postimages'):guard.require_runtime_postimages(self.root,manifest)
                else:
                    expected=guard.supplier_parent_audit_consumer_inputs(guard.supplier_mutation_consumer_inputs(guard.address_consumer_inputs(manifest['reviewedInputs'])))
                    current=d.dependency_consumer_inputs(expected)
                    self.assertEqual(74,len(current))
                    for path,value in current.items():self.assertEqual(value.split()[-1],d.canonical_blob(path,d.read(self.root,path)))
                    api=guard.BUILD_PROJECT
                    self.assertEqual(d.DEPENDENCIES[api]['after'],d.dependency_runtime_blob(api,manifest['buildProject']['gitBlob']))
                self.assertEqual({'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj'},d.require_dependency_runtime(self.root,actual,self.git))
                if hasattr(guard,'require_script_bindings'):
                    # Original function also queries rev-parse; use a bounded
                    # pure fixture callback for those exact paths, not real HEAD.
                    def query(root,*args):
                        if args[:1]==('rev-parse',):return (self.git_rows[args[1][5:]].split()[-1]+'\n').encode()
                        return self.git(root,*args)
                    guard.git=query;guard.require_script_bindings(self.root,manifest)

    def test_auth_actual_current_consumer_equality(self):
        path=self.root/'scripts/verify-procurement-auth-program.py'
        spec=importlib.util.spec_from_file_location('_dependency_auth',path);guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        manifest=d.parse(d.read(self.root,'tools/ProcurementAuthProgram.Tests/public-graph-supplier-omitted-size.json'))
        producer=manifest['intentionalSourceChanges']['reviewedInputs']
        binding=guard.require_consumer_binding(manifest);expected=dict(producer)
        for name,row in binding['changedInputs'].items():expected[name]=row['reviewedMetadata']
        expected=guard.supplier_parent_audit_consumer_inputs(guard.supplier_mutation_consumer_inputs(guard.address_consumer_inputs(guard.observation_consumer_inputs(expected))))
        current=d.dependency_consumer_inputs(expected)
        current[guard.HEALTH_ALIAS_RUNTIME if hasattr(guard,'HEALTH_ALIAS_RUNTIME') else 'Legacy.Maliev.ProcurementService.Api/Controllers/LegacyProcurementHealthController.cs']='100644 blob 4d81008ab101f21125dc4c6da7146453cc343bbf'
        guard.require_consumer_inputs(current,producer,manifest)
        changed=dict(current);changed['Directory.Build.props']='100644 blob '+'0'*40
        with self.assertRaises(ValueError):guard.require_consumer_inputs(changed,producer,manifest)

    def test_authenticated_historical_view_is_removed(self):
        with d.historical_view(self.root) as view:
            for name in d.TRANSFORMS:self.assertEqual(d.archived(self.root,name),(view/name).read_bytes())
        self.assertFalse(view.exists())

    def test_stale_dependency_file_even_after_reseal_is_refused(self):
        path='Directory.Build.props';self.reseal(path,d.archived(self.root,path))
        with self.assertRaises(ValueError):self.check()

    def test_unreviewed14_version_reseal_is_refused(self):
        path='Directory.Build.props';self.reseal(path,d.read(self.root,path).replace(b'10.0.13',b'10.0.14'))
        with self.assertRaises(ValueError):self.check()

    def test_removed_explicit_api_reference_is_refused(self):
        path='Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj'
        self.reseal(path,d.read(self.root,path).replace(b'    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="10.0.13" />\n',b''))
        with self.assertRaises(ValueError):self.check()

    def test_changed_runtime_or_producer_graph_is_refused(self):
        for path in ['Legacy.Maliev.ProcurementService.Api/Program.cs','tools/ProcurementAuthProgram.Tests/public-graph-supplier-omitted-size.json']:
            raw=d.read(self.root,path);self.reseal(path,raw+b' ')
            with self.assertRaises(ValueError):self.check()
            (self.root/path).write_bytes(raw)

    def test_changed_original_manifest_or_existing_consumer_is_refused(self):
        for path in ['docs/procurement-metadata-identity-contract.json','scripts/procurement_artifact_transport_consumer.py','scripts/procurement_address_null_consumer.py']:
            raw=d.read(self.root,path);self.reseal(path,raw+b' ')
            with self.assertRaises(ValueError):self.check()
            (self.root/path).write_bytes(raw)

    def test_changed_hook_assertion_or_baseline_is_refused(self):
        path='scripts/prepare-metadata-identity-baseline.py';self.reseal(path,d.read(self.root,path).replace(b'"Wrong immutable source baseline"',b'"Changed baseline"'))
        # Use a guaranteed byte change even if this spelling changes upstream.
        self.reseal(path,d.read(self.root,path)+b'\n# removed assertion\n')
        with self.assertRaises(ValueError):self.check()

    def test_archive_reseal_is_refused(self):
        path=next(iter(d.ARCHIVES.values()))['archive'];self.reseal(path,d.read(self.root,path)+b' ')
        with self.assertRaises(ValueError):self.check()

    def test_consistently_resealed_loaded_helper_is_refused(self):
        self.reseal(d.MODULE,d.read(self.root,d.MODULE)+b'\n')
        with self.assertRaisesRegex(ValueError,'loaded dependency verifier changed'):self.check()

    def test_resealed_new_controls_are_refused(self):
        self.reseal(d.CONTROLS,d.read(self.root,d.CONTROLS)+b'\n')
        with self.assertRaises(ValueError):self.check()

    def test_false_grant_types_and_duplicate_keys(self):
        profile=self.profile()
        for value in [True,0]:
            bad=copy.deepcopy(profile);bad['sdkGranted']=value;self.save(bad)
            with self.assertRaises(ValueError):self.check()
        self.save(profile);path=self.root/d.PROFILE;raw=path.read_bytes();path.write_bytes(b'{"schemaVersion":1,'+raw.lstrip()[1:])
        with self.assertRaises(ValueError):self.check()

    def test_unknown_current_source_and_wrong_head_are_refused(self):
        self.git_rows['unknown.cs']='100644 blob '+'0'*40
        with self.assertRaises(ValueError):self.check()
        self.git_rows.pop('unknown.cs');self.git_rows['Directory.Build.props']='100644 blob '+'0'*40
        with self.assertRaises(ValueError):self.check()

    def test_actual_working_file_change_without_reseal_is_refused(self):
        (self.root/'Directory.Build.props').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.check()

    def test_hardlink_refused(self):
        import os
        os.link(self.root/'Directory.Build.props',self.root/'same-source')
        with self.assertRaises(ValueError):d.read(self.root,'Directory.Build.props')

    def test_baseline_values_cannot_use_current_dependency_adapter(self):
        path='Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj'
        with self.assertRaises(ValueError):d.dependency_runtime_blob(path,'bd8fdadcbee41805eedd7a43c6eb8a02099e17d7')
        for script in [p for p in d.TRANSFORMS if '/prepare-' in p]:
            raw=d.read(self.root,script).decode()
            self.assertNotIn('dependency_runtime_blob(path, binding["gitBlob"])',raw)
            def baseline_calls(data):
                return [ast.dump(node,include_attributes=False) for node in ast.walk(ast.parse(data)) if isinstance(node,ast.Call)
                    and isinstance(node.func,ast.Name) and node.func.id in ('blob','git','read_bounded','tracked_inputs') and node.args
                    and any(isinstance(n,ast.Name) and n.id=='baseline' for n in ast.walk(node.args[0]))]
            self.assertEqual(baseline_calls(d.archived(self.root,script)),baseline_calls(raw))

    def test_actual_po_acquisition_and_all_eleven_restorations(self):
        path=self.root/'scripts/verify-po-header-hosted-red.py'
        spec=importlib.util.spec_from_file_location('_dependency_po',path);guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        contract=d.parse(d.read(self.root,'docs/procurement-po-header-hosted-red-contract.json'))
        def query(root,*args):
            if args==('rev-parse','HEAD'):return b'unit-head\n'
            if args==('status','--porcelain','--untracked-files=no'):return b''
            if args[:1]==('rev-parse',):return (self.git_rows[args[1][5:]].split()[-1]+'\n').encode()
            if args[:1]==('show',):return d.read(root,args[1][5:])
            return self.git(root,*args)
        guard.git=query
        sources=guard.candidate_sources(self.root,contract)
        self.assertEqual(11,len(sources))
        program=contract['baseline']['programPath'];absent=contract['baseline']['absentPath']
        (self.root/program).write_bytes(b'unit baseline replacement');(self.root/absent).unlink()
        evidence=Path(self.owner.name)/'evidence';evidence.mkdir()
        guard.restore(self.root,contract,sources,evidence,'unit-head')
        restored=d.parse((evidence/'restoration.json').read_bytes())
        self.assertEqual(11,len(restored['restored']))
        api='Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj'
        self.assertEqual(d.record(d.read(self.root,api))['sha256'],restored['restored'][api]['sha256'])
        for name in ['Directory.Build.props','Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj']:
            raw=d.read(self.root,name);(self.root/name).write_bytes(raw+b' ')
            with self.assertRaises(ValueError):guard.restore(self.root,contract,sources,evidence,'unit-head')
            (self.root/name).write_bytes(raw)

if __name__=='__main__':unittest.main()
