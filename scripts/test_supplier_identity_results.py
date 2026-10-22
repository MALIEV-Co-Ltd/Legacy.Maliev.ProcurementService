"""Synthetic controls only; fabricated UUIDs are never hosted test evidence."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
from test_procurement_address_null_consumer import AddressNullConsumerControls
from unittest import mock
import uuid
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
OLD_FILTER = "('FullyQualifiedName=Legacy.Maliev.ProcurementService.Tests.Integration.PurchaseOrderFileMetadataBindingTests.PrimitiveMembers_UsePublicTypedStringReader'\n                if phase == 'baseline' else 'FullyQualifiedName~PurchaseOrderFileMetadataBindingTests')"
NEW_FILTER = "'FullyQualifiedName~Legacy.Maliev.ProcurementService.Tests.Integration.' + profiles[family]"


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


guard = module("supplier_identity_guard", "verify-supplier-identity-results.py")
prep = module("supplier_identity_source", "prepare-supplier-identity-baseline.py")
observer = module("supplier_identity_observer", "observe-supplier-identity-providers.py")
CONTRACT = guard.read_json(HERE.parent / "docs/procurement-supplier-identity-contract.json")
NS = guard.NS


class IdentityResultControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.manifest = copy.deepcopy(CONTRACT)

    def fixtures(self, family):
        self.family = family
        self.baseline = self.root / (family + "-baseline")
        self.candidate = self.root / (family + "-candidate")
        for directory in (self.baseline, self.candidate):
            directory.mkdir(exist_ok=True)
            (directory / "coverage.cobertura.xml").write_text(
                '<coverage><packages><package><classes><class><lines><line number="1" hits="1"/></lines></class></classes></package></packages></coverage>',
                encoding="utf-8")
        self.base_doc = self.fixture("baseline")
        self.candidate_doc = self.fixture("candidate")

    def fixture(self, phase):
        profile = self.manifest["profiles"][self.family]
        root = ET.Element(NS + "TestRun")
        definitions = ET.SubElement(root, NS + "TestDefinitions")
        entries = ET.SubElement(root, NS + "TestEntries")
        results = ET.SubElement(root, NS + "Results")
        summary = ET.SubElement(root, NS + "ResultSummary", outcome="Failed" if phase == "baseline" else "Completed")
        count = profile["expectedCases"]
        failed = profile["baselineFailed"] if phase == "baseline" else 0
        ET.SubElement(summary, NS + "Counters", {"total":str(count), "executed":str(count),
                      "passed":str(count-failed), "failed":str(failed), **{key:"0" for key in guard.ADVERSE}})
        notices = ET.SubElement(summary, NS + "RunInfos") if failed else None
        for case in profile["cases"]:
            identity = str(uuid.uuid5(uuid.NAMESPACE_OID, "synthetic:" + case["name"]))
            execution = str(uuid.uuid5(uuid.NAMESPACE_URL, phase + ":synthetic:" + case["name"]))
            assembly = self.manifest["assemblyBindings"][phase]
            definition = ET.SubElement(definitions, NS + "UnitTest", id=identity, name=case["name"], storage=assembly["storage"])
            ET.SubElement(definition, NS + "Execution", id=execution)
            ET.SubElement(definition, NS + "TestMethod", name=case["method"], className=case["class"],
                          codeBase=assembly["codeBase"], adapterTypeName=assembly["adapterTypeName"])
            ET.SubElement(entries, NS + "TestEntry", testId=identity, executionId=execution)
            outcome = case["baselineOutcome"] if phase == "baseline" else "Passed"
            row = ET.SubElement(results, NS + "UnitTestResult", testName=case["name"], testId=identity, executionId=execution, outcome=outcome)
            if outcome == "Failed":
                failure = case["failure"]
                error = ET.SubElement(ET.SubElement(row, NS + "Output"), NS + "ErrorInfo")
                message = ("Assert.Equal() Failure: Values differ\nExpected: " + failure["expected"]
                           + "\nActual:   " + failure["actual"] if failure["kind"] == "status"
                           else "Assert.Equal() Failure: Strings differ\nExpected: " + failure["expected"])
                ET.SubElement(error, NS + "Message").text = message
                ET.SubElement(error, NS + "StackTrace").text = (
                    "   at " + case["class"] + "." + case["method"] + "() in /synthetic/"
                    + pathlib.Path(profile["testPath"]).name + ":line " + str(case["sourceLine"]))
                notice = ET.SubElement(notices, NS + "RunInfo", computerName="synthetic", outcome="Error",
                                       timestamp="2026-10-17T00:00:00.1234567Z")
                ET.SubElement(notice, NS + "Text").text = "[xUnit.net 00:00:00.10]     " + case["name"] + " [FAIL]"
        return root

    def write(self, directory, doc):
        ET.ElementTree(doc).write(directory / "results.trx", encoding="utf-8")

    def check_baseline(self):
        self.write(self.baseline, self.base_doc)
        return guard.verify(self.baseline, self.manifest, "baseline", self.family, 1)

    def check_candidate(self):
        self.check_baseline()
        self.write(self.candidate, self.candidate_doc)
        return guard.verify(self.candidate, self.manifest, "candidate", self.family, 0, self.baseline)

    def node(self, doc, path):
        return doc.find("./" + "/".join(NS + part for part in path.split("/")))

    def test_exact_both_families_and_shared_actual_identity_join(self):
        for family, passed, failed in (("id",26,29), ("address",30,22)):
            with self.subTest(family=family):
                self.fixtures(family)
                self.assertEqual((passed,failed), (self.check_baseline()["passed"],self.check_baseline()["failed"]))
                self.assertEqual(passed+failed, self.check_candidate()["passed"])

    def test_every_missing_case_refused(self):
        for family in ("id", "address"):
            self.fixtures(family)
            original = copy.deepcopy(self.candidate_doc)
            for index in range(len(self.manifest["profiles"][family]["cases"])):
                with self.subTest(family=family, index=index):
                    self.candidate_doc = copy.deepcopy(original)
                    parent = self.node(self.candidate_doc, "Results")
                    parent.remove(parent[index])
                    with self.assertRaises(ValueError): self.check_candidate()

    def test_unknown_duplicate_or_noncanonical_result_identity_refused(self):
        self.fixtures("id")
        original = copy.deepcopy(self.candidate_doc)
        second = self.node(original, "Results")[1]
        for key,value in (("testName","Foreign"), ("testName",second.get("testName")),
                          ("testId",str(uuid.uuid4())), ("testId",second.get("testId")),
                          ("executionId","invalid"), ("executionId",second.get("executionId")),
                          ("outcome","NotExecuted")):
            with self.subTest(key=key,value=value):
                self.candidate_doc = copy.deepcopy(original)
                self.node(self.candidate_doc,"Results")[0].set(key,value)
                with self.assertRaises(ValueError): self.check_candidate()

    def test_definition_entry_execution_method_and_class_must_join(self):
        self.fixtures("address")
        original = copy.deepcopy(self.candidate_doc)
        for path,key in (("TestEntries/TestEntry","executionId"),("TestDefinitions/UnitTest","name"),
                         ("TestDefinitions/UnitTest/Execution","id"),("TestDefinitions/UnitTest/TestMethod","name"),
                         ("TestDefinitions/UnitTest/TestMethod","className")):
            with self.subTest(path=path):
                self.candidate_doc = copy.deepcopy(original)
                self.node(self.candidate_doc,path).set(key,"foreign")
                with self.assertRaises(ValueError): self.check_candidate()

    def test_all16_counters_exact_and_closed(self):
        self.fixtures("id")
        original = copy.deepcopy(self.candidate_doc)
        for key in self.node(original,"ResultSummary/Counters").attrib:
            for missing in (False,True):
                with self.subTest(key=key,missing=missing):
                    self.candidate_doc = copy.deepcopy(original)
                    counters = self.node(self.candidate_doc,"ResultSummary/Counters")
                    if missing: del counters.attrib[key]
                    else: counters.set(key,"-1")
                    with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        self.node(self.candidate_doc,"ResultSummary/Counters").set("foreign","0")
        with self.assertRaises(ValueError): self.check_candidate()

    def test_nested_duplicate_or_foreign_containers_refused(self):
        self.fixtures("id")
        original = copy.deepcopy(self.candidate_doc)
        for tag in ("Results","TestDefinitions","TestEntries","ResultSummary","Counters"):
            for nested in (False,True):
                with self.subTest(tag=tag,nested=nested):
                    self.candidate_doc = copy.deepcopy(original)
                    found = self.candidate_doc.find(".//" + NS + tag)
                    parent = ET.SubElement(self.candidate_doc,NS+"Output") if nested else self.candidate_doc
                    parent.append(copy.deepcopy(found))
                    with self.assertRaises(ValueError): self.check_candidate()

    def test_namespace_root_and_moved_rows_refused(self):
        self.fixtures("address")
        original = copy.deepcopy(self.candidate_doc)
        for namespace in ("","{urn:foreign}"):
            self.candidate_doc = copy.deepcopy(original)
            for node in self.candidate_doc.iter(): node.tag = namespace + node.tag.removeprefix(NS)
            with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        self.candidate_doc.tag = NS+"Foreign"
        with self.assertRaises(ValueError): self.check_candidate()
        for tag in ("Results","TestDefinitions","TestEntries"):
            self.candidate_doc = copy.deepcopy(original)
            parent = self.node(self.candidate_doc,tag)
            row = parent[0]
            parent.remove(row)
            ET.SubElement(parent,NS+"Output").append(row)
            with self.assertRaises(ValueError): self.check_candidate()

    def test_every_failed_assertion_message_and_own_frame_required(self):
        for family in ("id","address"):
            self.fixtures(family)
            original = copy.deepcopy(self.base_doc)
            for index in range(self.manifest["profiles"][family]["baselineFailed"]):
                for field in ("Message","StackTrace"):
                    with self.subTest(family=family,index=index,field=field):
                        self.base_doc = copy.deepcopy(original)
                        list(self.base_doc.iter(NS+field))[index].text = "foreign assertion or frame"
                        with self.assertRaises(ValueError): self.check_baseline()

    def test_notice_bijection_metadata_and_zoned_timestamp_required(self):
        self.fixtures("id")
        original = copy.deepcopy(self.base_doc)
        for action in ("missing","duplicate","foreign","outcome","time","textchild"):
            self.base_doc = copy.deepcopy(original)
            parent = self.node(self.base_doc,"ResultSummary/RunInfos")
            if action == "missing": parent.remove(parent[0])
            elif action == "duplicate": parent.append(copy.deepcopy(parent[0]))
            elif action == "foreign": parent[0].find(NS+"Text").text = "[xUnit.net 00:00:00.10]     foreign [FAIL]"
            elif action == "outcome": parent[0].set("outcome","Warning")
            elif action == "time": parent[0].set("timestamp","2026-10-17T00:00:00")
            else: ET.SubElement(parent[0].find(NS+"Text"),NS+"Foreign")
            with self.assertRaises(ValueError): self.check_baseline()

    def test_candidate_adverse_errors_notices_and_summary_refused(self):
        self.fixtures("address")
        original = copy.deepcopy(self.candidate_doc)
        for tag in ("ErrorInfo","RunInfo"):
            self.candidate_doc = copy.deepcopy(original)
            ET.SubElement(self.candidate_doc,NS+tag)
            with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        self.node(self.candidate_doc,"ResultSummary").set("outcome","Failed")
        with self.assertRaises(ValueError): self.check_candidate()

    def test_candidate_revalidates_baseline_raw_and_preserved_proof(self):
        self.fixtures("id")
        self.check_baseline()
        self.write(self.candidate,self.candidate_doc)
        path = self.baseline/"supplier-identity-proof.json"
        raw = path.read_bytes()
        path.write_text("{}")
        with self.assertRaises(ValueError): guard.verify(self.candidate,self.manifest,"candidate","id",0,self.baseline)
        path.write_bytes(raw)
        self.node(self.base_doc,"Results")[0].set("testName","Foreign")
        self.write(self.baseline,self.base_doc)
        with self.assertRaises(ValueError): guard.verify(self.candidate,self.manifest,"candidate","id",0,self.baseline)

    def test_preserved_candidate_proof_is_immutable(self):
        self.fixtures("id")
        self.check_candidate()
        path = self.candidate/"supplier-identity-proof.json"
        path.write_text("{}")
        with self.assertRaises(ValueError): self.check_candidate()
        self.assertEqual("{}",path.read_text())

    def test_coverage_absent_nonexecutable_or_divergent_refused(self):
        for family in ("id","address"):
            self.fixtures(family)
            path = self.baseline/"coverage.cobertura.xml"
            original = path.read_bytes()
            path.unlink()
            with self.assertRaises(ValueError): self.check_baseline()
            path.write_text("<coverage/>")
            with self.assertRaises(ValueError): self.check_baseline()
            path.write_bytes(original)
            extra = self.baseline/"other"/"coverage.cobertura.xml"
            extra.parent.mkdir()
            extra.write_bytes(original+b" ")
            with self.assertRaises(ValueError): self.check_baseline()

    def test_wrong_phase_family_exit_and_manifest_roster_refused(self):
        self.fixtures("id")
        self.write(self.baseline,self.base_doc)
        for phase,family,code in (("baseline","id",0),("candidate","id",1),("foreign","id",1),("baseline","foreign",1)):
            with self.assertRaises(ValueError): guard.verify(self.baseline,self.manifest,phase,family,code)
        self.manifest["profiles"]["id"]["cases"].pop()
        with self.assertRaises(ValueError): self.check_baseline()


    def test_shared_case_guid_cannot_change_even_with_valid_internal_joins(self):
        self.fixtures("id")
        identity = str(uuid.uuid4())
        self.node(self.candidate_doc,"TestDefinitions/UnitTest").set("id",identity)
        self.node(self.candidate_doc,"TestEntries/TestEntry").set("testId",identity)
        self.node(self.candidate_doc,"Results/UnitTestResult").set("testId",identity)
        with self.assertRaises(ValueError): self.check_candidate()

    def test_individual_and_aggregate_coverage_read_limits(self):
        self.fixtures("id")
        self.write(self.baseline,self.base_doc)
        raw = (self.baseline/"coverage.cobertura.xml").read_bytes()
        for cap in ("MAX_COVERAGE_BYTES","MAX_COVERAGE_TOTAL_BYTES"):
            with self.subTest(cap=cap), mock.patch.object(guard,cap,len(raw)-1):
                with self.assertRaises(ValueError): guard.verify(self.baseline,self.manifest,"baseline","id",1)
        extra = self.baseline/"copy"/"coverage.cobertura.xml"
        extra.parent.mkdir()
        extra.write_bytes(raw)
        with mock.patch.object(guard,"MAX_COVERAGE_TOTAL_BYTES",2*len(raw)-1):
            with self.assertRaises(ValueError): guard.verify(self.baseline,self.manifest,"baseline","id",1)
        with mock.patch.object(guard,"MAX_COVERAGE_BYTES",len(raw)), \
                mock.patch.object(guard,"MAX_COVERAGE_TOTAL_BYTES",2*len(raw)):
            self.assertEqual(2,guard.verify(self.baseline,self.manifest,"baseline","id",1)["rawCopies"])


    def test_each_assembly_field_missing_foreign_debug_or_wrong_phase_refused(self):
        for family in ("id", "address"):
            self.fixtures(family)
            originals = {"baseline":copy.deepcopy(self.base_doc),"candidate":copy.deepcopy(self.candidate_doc)}
            for phase in ("baseline", "candidate"):
                binding = self.manifest["assemblyBindings"][phase]
                other = self.manifest["assemblyBindings"]["candidate" if phase == "baseline" else "baseline"]
                for field in ("storage", "codeBase", "adapterTypeName"):
                    values = [None, "", "foreign", other[field]]
                    if field == "storage":
                        values += [binding[field].replace("/release/","/debug/"),
                                   binding[field].replace("legacy.maliev.procurementservice.tests.dll","foreign.tests.dll"),
                                   binding[field].replace("/net10.0/","/net9.0/"), binding["codeBase"]]
                    elif field == "codeBase":
                        values += [binding[field].replace("/Release/","/Debug/"),
                                   binding[field].replace("Legacy.Maliev.ProcurementService.Tests.dll","Foreign.Tests.dll"),
                                   binding[field].replace("/net10.0/","/net9.0/"),binding["storage"]]
                    else:
                        values += ["executor://xunit/VsTestRunner3/netcoreapp/", "executor://nunit3testexecutor"]
                    for value in values:
                        if value == binding[field]:
                            continue
                        with self.subTest(family=family, phase=phase,field=field,value=value):
                            self.base_doc = copy.deepcopy(originals["baseline"])
                            self.candidate_doc = copy.deepcopy(originals["candidate"])
                            doc = self.base_doc if phase == "baseline" else self.candidate_doc
                            target = self.node(doc,"TestDefinitions/UnitTest")
                            if field != "storage":
                                target = target.find(NS+"TestMethod")
                            if value is None: target.attrib.pop(field,None)
                            else: target.set(field,value)
                            with self.assertRaises(ValueError):
                                if phase == "baseline": self.check_baseline()
                                else: self.check_candidate()

    def test_manifest_cannot_rebind_the_test_assembly_or_adapter(self):
        for phase in ("baseline","candidate"):
            for field in ("storage","codeBase","adapterTypeName"):
                self.fixtures("id")
                saved = copy.deepcopy(self.manifest["assemblyBindings"])
                self.manifest["assemblyBindings"][phase][field] = "foreign"
                doc = self.base_doc if phase == "baseline" else self.candidate_doc
                target = self.node(doc,"TestDefinitions/UnitTest")
                if field != "storage": target = target.find(NS+"TestMethod")
                target.set(field,"foreign")
                try:
                    with self.assertRaises(ValueError):
                        if phase == "baseline": self.check_baseline()
                        else: self.check_candidate()
                finally:
                    self.manifest["assemblyBindings"] = saved


class BoundedEvidenceControls(unittest.TestCase):
    def test_actual_maxplusone_read_and_inclusive_limit(self):
        for reader in ("guard","prep","observer"):
            for size in (4,5):
                stream = io.BytesIO(b"x"*size)
                path = mock.Mock()
                path.open.return_value.__enter__ = mock.Mock(return_value=stream)
                path.open.return_value.__exit__ = mock.Mock(return_value=False)
                tracked = mock.Mock(wraps=stream.read)
                stream.read = tracked
                if size == 4:
                    if reader == "guard": self.assertEqual(b"xxxx",guard.read_bounded(path,4))
                    elif reader == "prep": self.assertEqual(b"xxxx",prep.read_bounded(path,4,[4]))
                    else: self.assertEqual(b"xxxx",observer.read_phase_file(path,4,[4]))
                else:
                    with self.assertRaises(ValueError):
                        if reader == "guard": guard.read_bounded(path,4)
                        elif reader == "prep": prep.read_bounded(path,4,[4])
                        else: observer.read_phase_file(path,4,[4])
                tracked.assert_called_once_with(5)

    def test_utf8_nul_doctype_and_entity_refused_before_parse(self):
        for raw in (b"\xff",b"<TestRun>\x00</TestRun>",b"<!DOCTYPE TestRun><TestRun/>",b"<!ENTITY x 'value'><TestRun/>"):
            with self.assertRaises((ValueError,UnicodeDecodeError)): guard.parse_xml(raw)

    def test_finite_report_enumeration_refuses_second_trx_and_fifth_coverage(self):
        directory = mock.Mock()
        directory.rglob.return_value = iter(range(2))
        with self.assertRaises(ValueError): guard.reports(directory,"*.trx",1)
        directory.rglob.return_value = iter(range(5))
        with self.assertRaises(ValueError): guard.reports(directory,"coverage.cobertura.xml",4)
        directory.rglob.return_value = iter(range(2))
        with self.assertRaises(ValueError): prep.phase_reports(directory)
        directory.rglob.return_value = iter(range(2))
        with self.assertRaises(ValueError): observer.phase_reports(directory)

    def test_phase_and_operation_budget_exhaustion_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/"sample"
            path.write_bytes(b"12345")
            for function in (prep.read_bounded,observer.read_phase_file):
                with self.assertRaises(ValueError): function(path,100,[4])

    def test_json_proof_bound_is_applied_before_json_decode(self):
        with mock.patch.object(guard,"read_bounded",side_effect=ValueError("cap")) as reader, \
                mock.patch.object(guard.json,"loads") as decoder:
            with self.assertRaises(ValueError): guard.read_json(pathlib.Path("synthetic"))
            reader.assert_called_once_with(pathlib.Path("synthetic"),guard.MAX_JSON_BYTES)
            decoder.assert_not_called()

    def test_oversized_actual_trx_refused_before_parse(self):
        control = IdentityResultControls()
        control.setUp()
        try:
            control.fixtures("id")
            control.write(control.baseline,control.base_doc)
            with mock.patch.object(guard,"MAX_TRX_BYTES",4), mock.patch.object(guard,"parse_xml") as parser:
                with self.assertRaises(ValueError): guard.verify(control.baseline,control.manifest,"baseline","id",1)
                parser.assert_not_called()
        finally: control.doCleanups()


class SourceAndOwnershipControls(unittest.TestCase):
    def test_original107_harnesses_and_closed_runtime_roster(self):
        self.assertEqual({"id","address"},set(CONTRACT["profiles"]))
        self.assertEqual(107,sum(profile["expectedCases"] for profile in CONTRACT["profiles"].values()))
        self.assertEqual({prep.PROGRAM,prep.API_PROJECT,prep.CONVERTER,prep.FILE_CONVERTER,prep.METADATA_IDENTITY,prep.HEADER,prep.REPOSITORY,prep.SOURCE_FORMATTER,prep.SOURCE_MODELS} | set(prep.SUPPLIER_QUERY_RUNTIME),set(CONTRACT["runtimePostimages"]))
        for profile in CONTRACT["profiles"].values():
            raw = (HERE.parent/profile["testPath"]).read_bytes()
            header = ("blob " + str(len(raw)) + "\0").encode()
            self.assertEqual(profile["testBlob"],hashlib.sha1(header+raw).hexdigest())
        self.assertEqual("e8850889cb81b5bdf5bac5fdd1c55f2ed08cae8d",prep.BASE)

    def receipt(self):
        return {"phase":"candidate","family":"id","exitCode":0,"owningRun":"synthetic","owningAttempt":"1",
                "processExited":True,"normalFixtureDisposalProven":True,"resourcesAbsent":True,
                "uncertainResourcesPreserved":False,"errors":[],
                "processSessionCleanup":{"verified":True,"forcedCleanup":False,"handlesClosed":True,"launcherExited":True,
                                         "remainingSessionMembers":[],"cleanupErrors":[]},
                "disposalObservation":{"settled":True,"errors":[],"polls":[{"containerInventoryAvailable":True,
                    "volumeInventoryAvailable":True,"remainingContainerIds":[],"remainingVolumeNames":[]}]}}

    def phase(self, root, receipt):
        directory = root/"candidate-id"
        directory.mkdir()
        raw = b"synthetic raw identity document"
        digest = hashlib.sha256(raw).hexdigest()
        proof = {"phase":"candidate","family":"id","passed":55,"failed":0,"skipped":0,"trxSha256":digest}
        receipt["rawTrxSha256"] = digest
        (directory/"results.trx").write_bytes(raw)
        (directory/"supplier-identity-proof.json").write_text(json.dumps(proof))
        (directory/"provider-observation.json").write_text(json.dumps(receipt))
        return prep.require_phase(root,"candidate","id",[prep.MAX_OPERATION_BYTES])

    def test_normal_receipt_passes_and_every_cleanup_failure_refused(self):
        mutations = [(None,None,None),("root","processExited",False),("root","normalFixtureDisposalProven",False),
                     ("root","resourcesAbsent",False),("root","uncertainResourcesPreserved",True),
                     ("root","errors",["failed"]),("root","owningRun","foreign"),("root","exitCode",True),
                     ("processSessionCleanup","verified",False),("processSessionCleanup","forcedCleanup",True),
                     ("processSessionCleanup","handlesClosed",False),("processSessionCleanup","launcherExited",False),
                     ("processSessionCleanup","remainingSessionMembers",[123]),("processSessionCleanup","cleanupErrors",["failed"]),
                     ("disposalObservation","settled",False),("disposalObservation","errors",["failed"]),
                     ("poll","containerInventoryAvailable",False),("poll","volumeInventoryAvailable",False),
                     ("poll","remainingContainerIds",["foreign"]),("poll","remainingVolumeNames",["foreign"])]
        for section,key,value in mutations:
            with self.subTest(section=section,key=key), tempfile.TemporaryDirectory() as directory, \
                    mock.patch.dict(os.environ,{"GITHUB_RUN_ID":"synthetic","GITHUB_RUN_ATTEMPT":"1"}):
                receipt = self.receipt()
                if section:
                    target = receipt if section == "root" else receipt["disposalObservation"]["polls"][-1] if section == "poll" else receipt[section]
                    target[key] = value
                    with self.assertRaises(ValueError): self.phase(pathlib.Path(directory),receipt)
                else: self.assertTrue(self.phase(pathlib.Path(directory),receipt)["normalDisposal"])

    def test_observer_is_exact_approved_ownership_clone_with_only_declared_filter_delta(self):
        original = (HERE/"observe-file-metadata-providers.py").read_text(encoding="utf-8")
        expected = original.replace("def observe(workspace, output, phase):","def observe(workspace, output, phase, family):")
        expected = expected.replace("    command = ['dotnet',", "    profiles = {'id': 'ProcurementSupplierIgnoredIdTests', 'address': 'ProcurementSupplierIgnoredAddressIdTests'}\n    require(family in profiles, 'Unknown supplier identity family')\n    command = ['dotnet',")
        expected = expected.replace(OLD_FILTER,NEW_FILTER)
        expected = expected.replace("{'phase':phase, 'startedAtUtc':observed_at", "{'phase':phase, 'family':family, 'startedAtUtc':observed_at")
        expected = expected.replace("'purpose':'File metadata isolated16 baseline or108 candidate phase'", "'purpose':'Supplier ignored identity isolated55 or52 baseline/candidate phase'")
        expected = expected.replace("'hostedJobLeaseMinutes':30", "'hostedJobLeaseMinutes':45")
        expected = expected.replace("sys.argv[3])","sys.argv[3],sys.argv[4])")
        self.assertEqual(expected,(HERE/"observe-supplier-identity-providers.py").read_text(encoding="utf-8"))



class TypedSupplierProvenanceControls(unittest.TestCase):
    def test_closed_git_blob_record_shape_and_exact_digest_are_required(self):
        for record in CONTRACT["runtimePostimages"].values():
            self.assertEqual(record["gitBlob"], prep.git_blob_record(record))
            for invalid in (record["gitBlob"], None, {}, {"sha256": "a" * 64},
                            {"gitBlob": record["gitBlob"], "extra": True},
                            {"gitBlob": "a" * 39}, {"gitBlob": "G" * 40},
                            {"gitBlob": record["gitBlob"].upper()}, {"gitBlob": 7}):
                with self.subTest(invalid_type=type(invalid).__name__), self.assertRaises(ValueError):
                    prep.git_blob_record(invalid)

    def test_missing_or_wrong_format_and_runtime_roster_are_refused(self):
        for mutation in ("missing-format", "wrong-format", "missing-record", "extra-record", "wrong-record"):
            changed = copy.deepcopy(CONTRACT)
            if mutation == "missing-format":
                del changed["runtimeBindingFormat"]
            elif mutation == "wrong-format":
                changed["runtimeBindingFormat"] = "unreviewed"
            elif mutation == "missing-record":
                changed["runtimePostimages"].pop(next(iter(changed["runtimePostimages"])))
            elif mutation == "wrong-record":
                changed["runtimePostimages"][next(iter(changed["runtimePostimages"]))] = {"gitBlob": "not-a-blob"}
            else:
                changed["runtimePostimages"]["unreviewed"] = {"gitBlob": "a" * 40}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prep.runtime_bindings(changed)



    def test_every_validly_shaped_but_wrong_git_object_is_refused(self):
        actual = {path: prep.supplier_mutation_runtime_blob(path, record["gitBlob"])
                  for path, record in CONTRACT["runtimePostimages"].items()}
        with mock.patch.object(prep, "blob", side_effect=lambda root, path: actual[path]):
            prep.require_runtime_postimages(pathlib.Path("."), CONTRACT)
            for path in actual:
                changed = copy.deepcopy(CONTRACT)
                changed["runtimePostimages"][path] = {"gitBlob": "0" * 40}
                with self.subTest(path=path), self.assertRaises(ValueError):
                    prep.require_runtime_postimages(pathlib.Path("."), changed)


# Include current-consumer rejection controls in this workflow-selected module.
from test_procurement_address_null_consumer import SupplierMutationConsumerControls


if __name__ == "__main__":
    unittest.main()
