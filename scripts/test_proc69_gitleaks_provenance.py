"""Synthetic controls only; no scanner findings or customer data are test inputs."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proc69_provenance", HERE / "proc69_gitleaks_provenance.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
EXPECTED_GROUP = "      - name: Check out exact tested PR69 scanner provenance\n        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n        with:\n          repository: MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService\n          ref: d6d75eec7e3b02afb4fa45d533dc35f4b71697cd\n          path: .proc69-gitleaks-scan\n          fetch-depth: 1\n          persist-credentials: false\n      - name: Temporarily diagnose PR69 gitleaks provenance privately\n        shell: bash\n        timeout-minutes: 6\n        run: bash scripts/run_proc69_gitleaks_diagnostic.sh\n"


class ProvenanceControls(unittest.TestCase):
    def finding(self):
        return {"RuleID":"generic-api-key", "File":"tests/Fixture.cs", "StartLine":12,
                "Commit":"a"*40, "Match":"SYNTHETIC", "Secret":"SYNTHETIC",
                "Entropy":9.9, "Message":"SYNTHETIC", "Fingerprint":"SYNTHETIC"}

    def provenance(self, data, code=1):
        return diagnostic.safe_provenance(data, frozenset(("tests/Fixture.cs",)), frozenset(("a"*40,)), code)

    def test_only_reviewed_four_fields_are_projected(self):
        finding = self.finding()
        result = self.provenance(json.dumps([finding]).encode())
        self.assertEqual([{key:finding[key] for key in ("RuleID","File","StartLine","Commit")}],result)
        self.assertNotIn("SYNTHETIC",json.dumps(result))
        self.assertNotIn("Fingerprint",json.dumps(result))

    def test_empty_success_and_nonempty_leak_exit_must_agree(self):
        self.assertEqual([],self.provenance(b"[]",0))
        for code in (1,2,124,True):
            with self.subTest(code=code), self.assertRaises(ValueError):
                self.provenance(b"[]",code)
        with self.assertRaises(ValueError):
            self.provenance(json.dumps([self.finding()]).encode(),0)

    def test_invalid_count_shape_duplicates_and_constants_are_refused(self):
        values = [b"{}",b"[0]",b"null",b'[{"RuleID":"x","RuleID":"y"}]',
                  b"[NaN]",b"[Infinity]",json.dumps([{}]*1001).encode(),b"\xff"]
        for raw in values:
            with self.subTest(size=len(raw)), self.assertRaises((ValueError,UnicodeError)):
                self.provenance(raw)

    def test_every_required_field_shape_is_checked(self):
        finding = self.finding()
        for field,value in (("RuleID","bad\nrule"),("RuleID","x"*129),("File","../unsafe"),
                            ("File","/absolute"),("File","tests/./Fixture.cs"),
                            ("StartLine",True),("StartLine",0),("StartLine",10000001),
                            ("Commit","A"*40),("Commit","unknown")):
            changed = dict(finding)
            changed[field] = value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.provenance(json.dumps([finding,changed]).encode())
        for field in ("RuleID","File","StartLine","Commit"):
            changed = dict(finding)
            del changed[field]
            with self.subTest(missing=field),self.assertRaises(ValueError):
                self.provenance(json.dumps([changed]).encode())

    def test_unknown_safe_path_or_commit_refuses_whole_report(self):
        for field,value in (("File","staff/PersonalName/profile.txt"),("File","tests/Unknown.cs"),
                            ("Commit","b"*40)):
            changed = self.finding()
            changed[field] = value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.provenance(json.dumps([self.finding(),changed]).encode())

    def test_bound_scope_has_only_exact_procurement_commit_and252_paths(self):
        paths,commits = diagnostic.reviewed_scope()
        self.assertEqual(frozenset(("d6d75eec7e3b02afb4fa45d533dc35f4b71697cd",)),commits)
        self.assertEqual(252,len(paths))
        self.assertIn("Legacy.Maliev.ProcurementService.Api/Program.cs",paths)
        self.assertNotIn("scripts/proc69-gitleaks-provenance-scope.json",paths)
        self.assertFalse(any(path.startswith("Legacy.Maliev.EmployeeService") for path in paths))

    def test_scope_byte_drift_refuses_before_any_inventory_is_trusted(self):
        raw = diagnostic.bounded_read(diagnostic.SCOPE,diagnostic.MAX_SOURCE_BYTES)
        with mock.patch.object(diagnostic,"bounded_read",return_value=raw+b" "):
            with self.assertRaises(ValueError):
                diagnostic.reviewed_scope()


class PrivateSinkControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private = self.root/"proc69-gitleaks-synthetic"
        self.private.mkdir(mode=0o700)
        self.paths = tuple(self.private/name for name in ("report.json","stdout.log","stderr.log"))
        finding = {"RuleID":"generic-api-key","File":"tests/Fixture.cs","StartLine":12,"Commit":"a"*40,
                   "Secret":"SYNTHETIC","Match":"SYNTHETIC"}
        for path,raw in zip(self.paths,(json.dumps([finding]).encode(),b"RAW_OUT",b"RAW_ERR")):
            with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as stream:
                stream.write(raw)
        self.scope = mock.patch.object(diagnostic,"reviewed_scope",
                     return_value=(frozenset(("tests/Fixture.cs",)),frozenset(("a"*40,))))
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.environment = mock.patch.dict(os.environ,{"RUNNER_TEMP":str(self.root)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def main(self):
        stdout,stderr = io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            status = diagnostic.main([*(str(path) for path in self.paths),"1"])
        return status,stdout.getvalue(),stderr.getvalue()

    def test_private_sinks_only_emit_validated_metadata(self):
        code,out,err = self.main()
        self.assertEqual(0,code)
        self.assertEqual("",err)
        self.assertEqual({"RuleID","File","StartLine","Commit"},set(json.loads(out)))
        for marker in ("SYNTHETIC","RAW_OUT","RAW_ERR"):
            self.assertNotIn(marker,out+err)

    def test_invalid_late_row_never_emits_partial_metadata_or_values(self):
        path = self.paths[0]
        rows = json.loads(path.read_bytes())
        invalid = dict(rows[0],File="staff/UnknownPerson/profile.txt")
        path.write_bytes(json.dumps([rows[0],invalid]).encode())
        code,out,err = self.main()
        self.assertEqual((2,"","Gitleaks provenance diagnostic refused.\n"),(code,out,err))
        self.assertNotIn("UnknownPerson",out+err)

    def test_every_sink_is_actually_bounded_before_projection(self):
        for index in range(3):
            with self.subTest(index=index):
                original = self.paths[index].read_bytes()
                self.paths[index].write_bytes(b"x"*1025)
                with mock.patch.object(diagnostic,"MAX_PRIVATE_BYTES",1024), \
                        mock.patch.object(diagnostic,"safe_provenance") as projection:
                    code,out,err = self.main()
                    projection.assert_not_called()
                self.assertEqual(2,code)
                self.assertEqual("",out)
                self.assertEqual("Gitleaks provenance diagnostic refused.\n",err)
                self.paths[index].write_bytes(original)

    def test_inclusive_actual_read_limits_and_maxplusone_are_used(self):
        path = self.paths[1]
        path.write_bytes(b"xxxx")
        self.assertEqual(b"xxxx",diagnostic.bounded_read(path,4,private=True))
        path.write_bytes(b"xxxxx")
        with self.assertRaises(ValueError):diagnostic.bounded_read(path,4,private=True)
        # A private regular file is read through its descriptor at exactly cap+1.
        descriptor = mock.Mock()
        descriptor.fileno.return_value = 123
        descriptor.read.return_value = b"xxxxx"
        manager = mock.MagicMock()
        manager.__enter__.return_value = descriptor
        metadata = os.stat(self.paths[0])
        with mock.patch.object(diagnostic.os,"open",return_value=123), \
                mock.patch.object(diagnostic.os,"fdopen",return_value=manager), \
                mock.patch.object(diagnostic.os,"fstat",return_value=metadata):
            with self.assertRaises(ValueError):diagnostic.bounded_read(path,4,private=True)
        descriptor.read.assert_called_once_with(5)

    def test_public_file_or_parent_permissions_are_refused(self):
        for path in self.paths:
            path.chmod(0o644)
            code,out,_ = self.main()
            self.assertEqual((2,""),(code,out))
            path.chmod(0o600)
        self.private.chmod(0o755)
        code,out,_ = self.main()
        self.assertEqual((2,""),(code,out))

    def test_symlink_sink_is_refused_without_values(self):
        path = self.paths[1]
        path.unlink()
        path.symlink_to(self.paths[0])
        code,out,err = self.main()
        self.assertEqual((2,"","Gitleaks provenance diagnostic refused.\n"),(code,out,err))

    def test_unknown_commit_is_silent_for_the_entire_report(self):
        path = self.paths[0]
        rows = json.loads(path.read_bytes())
        rows.append(dict(rows[0],Commit="b"*40))
        path.write_bytes(json.dumps(rows).encode())
        self.assertEqual((2,"","Gitleaks provenance diagnostic refused.\n"),self.main())


class HostedSourceControls(unittest.TestCase):
    def test_private_scanner_sinks_exact_pin_limits_and_exit_cleanup(self):
        script = (HERE/"run_proc69_gitleaks_diagnostic.sh").read_text(encoding="utf-8")
        self.assertIn("umask 077",script)
        self.assertIn('private_dir="$(mktemp -d "${RUNNER_TEMP}/proc69-gitleaks-XXXXXX")"',script)
        self.assertIn("trap cleanup EXIT",script)
        self.assertIn('rm -f -- "$report" "$scan_stdout" "$scan_stderr" "$scanner" 2>/dev/null',script)
        self.assertIn('rmdir -- "$private_dir" 2>/dev/null',script)
        self.assertIn("ulimit -f 4096 || exit 2",script)
        self.assertIn("ulimit -t 120 || exit 2",script)
        self.assertIn('timeout 120s "$scanner" git --redact --exit-code 1 --report-format json --report-path "$report"',script)
        self.assertIn(') > "$scan_stdout" 2> "$scan_stderr"\nscan_status=$?',script)
        self.assertIn("github.com/zricethezav/gitleaks/v8@6eaad039603a4de39fddd1cf5f727391efe9974e",script)
        self.assertIn('exit "$scan_status"',script)
        self.assertIn('exit "$parser_status"',script)
        self.assertNotIn("--verbose",script)
        self.assertNotIn("--exit-code 0",script)
        self.assertEqual(["cat runner-results/proc69-gitleaks-provenance.jsonl"],
            [line.strip() for line in script.splitlines() if line.strip().startswith(("cat ","tee "))])
        for line in script.splitlines():
            if '"$scan_stdout"' in line or '"$scan_stderr"' in line:
                self.assertTrue(line.strip().startswith(("if ! rm -f",") > ","python3 -B scripts/proc69_gitleaks_provenance.py")),
                                "Unreviewed raw scanner stream sink")

    def test_wrapper_bash_syntax(self):
        result = subprocess.run(["bash","-n",str(HERE/"run_proc69_gitleaks_diagnostic.sh")],
                                capture_output=True,timeout=10,check=False)
        self.assertEqual(0,result.returncode)

    def test_temporary_normal_job_preserves_all_original_required_steps(self):
        import hashlib
        workflow = (HERE.parent/".github/workflows/_build-and-test.yml").read_text(encoding="utf-8")
        self.assertEqual(1,workflow.count(EXPECTED_GROUP))
        restored = workflow.replace(EXPECTED_GROUP,"").replace("    timeout-minutes: 45\n","",1)
        self.assertEqual("087b52a12b6c51a2b2f10a520e738d7e004dd0c77c83505add3626e78cfc4455",hashlib.sha256(restored.encode()).hexdigest())
        self.assertIn("permissions:\n  contents: read",workflow)
        self.assertNotIn("workflow_dispatch:",workflow)
        self.assertIn("-O -B -m unittest discover", (HERE/"run_proc69_gitleaks_diagnostic.sh").read_text())
        self.assertIn("fetch-depth: 1",EXPECTED_GROUP)
        self.assertIn("persist-credentials: false",EXPECTED_GROUP)

    def test_workflow_structural_guard_requires_the_exact_temporary_group(self):
        source = (HERE.parent/"Legacy.Maliev.ProcurementService.Tests/Workflows/WorkflowContractTests.cs").read_text()
        self.assertIn("steps = ValidateTemporaryGitleaksDiagnosticGroup(steps);",source)
        self.assertIn("steps.Children.Count != 20",source)
        self.assertIn("RequireExactProofNode(steps.Children[index + 15], proof.Children[index]);",source)
        self.assertIn("index is not (15 or 16)",source)


if __name__ == "__main__":
    unittest.main()
