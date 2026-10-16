"""Synthetic acceptance controls; fixtures are not actual hosted test evidence."""
import copy
import io
import importlib.util
import json
import hashlib
import os
import pathlib
import re
import tempfile
import unittest
from unittest import mock
import uuid
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("metadata", pathlib.Path(__file__).with_name("verify-file-metadata-binding-results.py"))
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
CONTRACT = guard.read_json(pathlib.Path(__file__).parents[1] / "docs" / "procurement-file-metadata-binding-contract.json")
NS = guard.NS
OBSERVER_READ_HELPERS = "MAX_LOG_BYTES = 4 * 1024 * 1024\nMAX_TRX_BYTES = 16 * 1024 * 1024\nMAX_PHASE_READ_BYTES = 20 * 1024 * 1024\n\n\ndef read_phase_file(path, maximum, budget):\n    limit = min(maximum, budget[0])\n    require(limit >= 0, 'Negative phase evidence budget')\n    with path.open('rb') as stream:\n        raw = stream.read(limit + 1)\n    require(0 < len(raw) <= limit, 'Phase evidence exceeds the bounded reader')\n    budget[0] -= len(raw)\n    return raw\n\n\ndef phase_reports(output):\n    reports = []\n    for path in output.rglob('*.trx'):\n        require(not reports, 'Require exactly one actual filtered TRX')\n        reports.append(path)\n    return reports\n\n\ndef phase_document(raw):\n    text = raw.decode('utf-8-sig', errors='strict')\n    require(not re.search(r'<!\\s*(DOCTYPE|ENTITY)\\b', text, re.IGNORECASE), 'DTD/entity declarations forbidden')\n    return ET.fromstring(text)\n\n\ndef read_phase_payload(output):\n    budget = [MAX_PHASE_READ_BYTES]\n    log_raw = read_phase_file(output/'test-console.log', MAX_LOG_BYTES, budget)\n    reports = phase_reports(output)\n    require(len(reports) == 1, 'Require actual filtered TRX for container ownership')\n    trx_raw = read_phase_file(reports[0], MAX_TRX_BYTES, budget)\n    return log_raw.decode('utf-8-sig', errors='strict'), phase_document(trx_raw), trx_raw\n\n\n"

PREP_SPEC = importlib.util.spec_from_file_location("metadata_source", pathlib.Path(__file__).with_name("prepare-file-metadata-baseline.py"))
prep = importlib.util.module_from_spec(PREP_SPEC)
PREP_SPEC.loader.exec_module(prep)

OBS_SPEC = importlib.util.spec_from_file_location("metadata_observer", pathlib.Path(__file__).with_name("observe-file-metadata-providers.py"))
observer = importlib.util.module_from_spec(OBS_SPEC)
OBS_SPEC.loader.exec_module(observer)




class FileMetadataResultControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.manifest = copy.deepcopy(CONTRACT)
        self.baseline = self.root / "baseline"
        self.candidate = self.root / "candidate"
        self.baseline.mkdir()
        self.candidate.mkdir()
        for directory in (self.baseline, self.candidate):
            (directory / "coverage.cobertura.xml").write_text(
                '<coverage><packages><package><classes><class><lines><line number="1" hits="1"/></lines></class></classes></package></packages></coverage>',
                encoding="utf-8")
        self.base_doc = self.fixture("baseline")
        self.candidate_doc = self.fixture("candidate")

    def fixture(self, phase):
        cases = self.manifest["baseline"]["cases"] if phase == "baseline" else self.manifest["candidate"]
        root = ET.Element(NS + "TestRun")
        definitions = ET.SubElement(root, NS + "TestDefinitions")
        entries = ET.SubElement(root, NS + "TestEntries")
        results = ET.SubElement(root, NS + "Results")
        summary = ET.SubElement(root, NS + "ResultSummary", outcome="Failed" if phase == "baseline" else "Completed")
        total, passed, failed = (16, 6, 10) if phase == "baseline" else (108, 108, 0)
        values = {"total": str(total), "executed": str(total), "passed": str(passed), "failed": str(failed),
                  **{key: "0" for key in guard.ADVERSE}}
        ET.SubElement(summary, NS + "Counters", values)
        notices = ET.SubElement(summary, NS + "RunInfos") if failed else None
        for case in cases:
            identity = str(uuid.uuid5(uuid.NAMESPACE_OID, case["name"]))
            execution = str(uuid.uuid5(uuid.NAMESPACE_URL, phase + ":" + case["name"]))
            definition = ET.SubElement(definitions, NS + "UnitTest", id=identity, name=case["name"])
            ET.SubElement(definition, NS + "Execution", id=execution)
            ET.SubElement(definition, NS + "TestMethod", name=case["method"], className=self.manifest["testClass"])
            ET.SubElement(entries, NS + "TestEntry", testId=identity, executionId=execution)
            outcome = case["expectedOutcome"] if phase == "baseline" else "Passed"
            row = ET.SubElement(results, NS + "UnitTestResult", testName=case["name"], testId=identity, executionId=execution, outcome=outcome)
            if outcome == "Failed":
                error = ET.SubElement(ET.SubElement(row, NS + "Output"), NS + "ErrorInfo")
                ET.SubElement(error, NS + "Message").text = case["expectedMessage"]
                ET.SubElement(error, NS + "StackTrace").text = "\n".join(
                    "   at " + self.manifest["testClass"] + "." + frame["method"]
                    + "(String value) in /fixture/PurchaseOrderFileMetadataBindingTests.cs:line " + str(frame["line"])
                    for frame in self.manifest["baseline"]["requiredUserFrames"])
                notice = ET.SubElement(notices, NS + "RunInfo", computerName="synthetic", outcome="Error", timestamp="2026-10-17T00:00:00.1234567Z")
                ET.SubElement(notice, NS + "Text").text = "[xUnit.net 00:00:00.10]     " + case["name"] + " [FAIL]"
        return root

    def write(self, directory, doc):
        ET.ElementTree(doc).write(directory / "results.trx", encoding="utf-8")

    def check_baseline(self):
        self.write(self.baseline, self.base_doc)
        return guard.verify(self.baseline, self.manifest, "baseline", 1)

    def check_candidate(self):
        self.check_baseline()
        self.write(self.candidate, self.candidate_doc)
        return guard.verify(self.candidate, self.manifest, "candidate", 0, self.baseline)

    def test_exact_namespace_summary_rosters_and_shared_ids_pass(self):
        self.assertEqual(10, self.check_baseline()["failed"])
        self.assertEqual(108, self.check_candidate()["passed"])

    def test_wrong_phase_or_process_exit_refused(self):
        self.write(self.baseline, self.base_doc)
        for phase, code in (("baseline", 0), ("candidate", 1), ("unknown", 0)):
            with self.subTest(phase=phase, code=code):
                with self.assertRaises(ValueError): guard.verify(self.baseline, self.manifest, phase, code)

    def test_missing_each_actual_case_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for index in range(108):
            with self.subTest(index=index):
                self.candidate_doc = copy.deepcopy(original)
                parent = self.candidate_doc.find("./" + NS + "Results")
                parent.remove(parent[index])
                with self.assertRaises(ValueError): self.check_candidate()

    def test_foreign_or_duplicate_actual_identity_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for key, value in (("testName", "Foreign"), ("testId", str(uuid.uuid4())), ("executionId", "foreign"), ("outcome", "NotExecuted")):
            with self.subTest(key=key):
                self.candidate_doc = copy.deepcopy(original)
                self.candidate_doc.find("./" + NS + "Results/" + NS + "UnitTestResult").set(key, value)
                with self.assertRaises(ValueError): self.check_candidate()

    def test_entry_definition_method_execution_mismatch_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for path, key, value in (
                ("TestEntries/TestEntry", "executionId", str(uuid.uuid4())),
                ("TestDefinitions/UnitTest", "name", "Foreign"),
                ("TestDefinitions/UnitTest/Execution", "id", str(uuid.uuid4())),
                ("TestDefinitions/UnitTest/TestMethod", "className", "Foreign"),
                ("TestDefinitions/UnitTest/TestMethod", "name", "Foreign")):
            with self.subTest(path=path):
                self.candidate_doc = copy.deepcopy(original)
                self.candidate_doc.find("./" + "/".join(NS + part for part in path.split("/"))).set(key, value)
                with self.assertRaises(ValueError): self.check_candidate()

    def test_all16_counter_missing_value_or_extra_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        keys = list(original.find("./" + NS + "ResultSummary/" + NS + "Counters").attrib)
        for key in keys:
            for missing in (False, True):
                with self.subTest(key=key, missing=missing):
                    self.candidate_doc = copy.deepcopy(original)
                    counters = self.candidate_doc.find("./" + NS + "ResultSummary/" + NS + "Counters")
                    if missing: del counters.attrib[key]
                    else: counters.set(key, "1")
                    with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        self.candidate_doc.find("./" + NS + "ResultSummary/" + NS + "Counters").set("foreign", "0")
        with self.assertRaises(ValueError): self.check_candidate()

    def test_duplicate_or_nested_summary_counters_containers_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for name in ("ResultSummary", "Counters", "Results", "TestDefinitions", "TestEntries"):
            for nested in (False, True):
                with self.subTest(name=name, nested=nested):
                    self.candidate_doc = copy.deepcopy(original)
                    node = self.candidate_doc.find(".//" + NS + name)
                    parent = ET.SubElement(self.candidate_doc, NS + "Output") if nested else self.candidate_doc
                    parent.append(copy.deepcopy(node))
                    with self.assertRaises(ValueError): self.check_candidate()

    def test_moved_rows_and_duplicate_execution_nodes_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for name in ("Results", "TestDefinitions", "TestEntries"):
            with self.subTest(name=name):
                self.candidate_doc = copy.deepcopy(original)
                parent = self.candidate_doc.find("./" + NS + name)
                row = parent[0]
                parent.remove(row)
                ET.SubElement(parent, NS + "Output").append(row)
                with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        definition = self.candidate_doc.find("./" + NS + "TestDefinitions/" + NS + "UnitTest")
        definition.append(copy.deepcopy(definition.find("./" + NS + "Execution")))
        with self.assertRaises(ValueError): self.check_candidate()

    def test_wrong_root_or_namespace_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for namespace in ("", "{urn:foreign}"):
            with self.subTest(namespace=namespace):
                self.candidate_doc = copy.deepcopy(original)
                for node in self.candidate_doc.iter():
                    node.tag = namespace + node.tag.removeprefix(NS)
                with self.assertRaises(ValueError): self.check_candidate()
        self.candidate_doc = copy.deepcopy(original)
        self.candidate_doc.tag = NS + "Foreign"
        with self.assertRaises(ValueError): self.check_candidate()

    def test_candidate_adverse_notice_or_error_refused(self):
        original = copy.deepcopy(self.candidate_doc)
        for tag in ("RunInfo", "ErrorInfo"):
            with self.subTest(tag=tag):
                self.candidate_doc = copy.deepcopy(original)
                ET.SubElement(self.candidate_doc, NS + tag, outcome="Error")
                with self.assertRaises(ValueError): self.check_candidate()

    def test_baseline_typed_chain_path_token_position_refused(self):
        original = copy.deepcopy(self.base_doc)
        for before, after in (("UpsertPurchaseOrderFileRequest", "UpsertPurchaseOrderRequest"),
                              ("$.Bucket", "$.ObjectName"),
                              ("'Number'", "'StartObject'"),
                              ("System.InvalidOperationException", "System.IO.IOException"),
                              ("LineNumber: 0", "LineNumber: 1")):
            with self.subTest(before=before):
                self.base_doc = copy.deepcopy(original)
                node = next(node for node in self.base_doc.iter(NS + "Message") if before in (node.text or ""))
                node.text = node.text.replace(before, after)
                with self.assertRaises(ValueError): self.check_baseline()

    def test_baseline_byte_position_and_duplicate_execution_refused(self):
        self.base_doc = self.fixture("baseline")
        message = next(self.base_doc.iter(NS + "Message"))
        message.text = re.sub(r"BytePositionInLine: (\d+)", lambda match: "BytePositionInLine: " + str(int(match.group(1)) + 1), message.text)
        with self.assertRaises(ValueError): self.check_baseline()
        self.base_doc = self.fixture("baseline")
        rows = self.candidate_doc.find("./" + NS + "Results")
        rows[1].set("executionId", rows[0].get("executionId"))
        with self.assertRaises(ValueError): self.check_candidate()

    def test_missing_or_foreign_prefixed_user_frame_refused(self):
        original = copy.deepcopy(self.base_doc)
        for frame in self.manifest["baseline"]["requiredUserFrames"]:
            for mode in ("remove", "prefix", "wrong_line", "foreign_file"):
                with self.subTest(frame=frame["method"], mode=mode):
                    self.base_doc = copy.deepcopy(original)
                    node = next(self.base_doc.iter(NS + "StackTrace"))
                    lines = node.text.splitlines()
                    index = next(index for index, line in enumerate(lines) if "." + frame["method"] + "(" in line)
                    if mode == "remove": lines.pop(index)
                    elif mode == "prefix": lines[index] = "diagnostic: " + lines[index]
                    elif mode == "wrong_line": lines[index] = lines[index].replace(":line " + str(frame["line"]), ":line 99999")
                    else: lines[index] = lines[index].replace("/PurchaseOrderFileMetadataBindingTests.cs", "/ForeignPurchaseOrderFileMetadataBindingTests.cs")
                    node.text = "\n".join(lines)
                    with self.assertRaises(ValueError): self.check_baseline()

    def test_framework_frames_remain_diagnostic(self):
        original_directory = self.baseline
        coverage = (original_directory / "coverage.cobertura.xml").read_bytes()
        for index, frame in enumerate(("   at Framework.OptionalConverter.Read()", "   at Framework.OptionalReader.GetString()")):
            self.baseline = self.root / ("diagnostic-" + str(index))
            self.baseline.mkdir()
            (self.baseline / "coverage.cobertura.xml").write_bytes(coverage)
            self.base_doc = self.fixture("baseline")
            for node in self.base_doc.iter(NS + "StackTrace"): node.text += "\n" + frame
            self.assertEqual(10, self.check_baseline()["failed"])
        self.baseline = original_directory

    def test_baseline_notice_bijection_and_metadata_refused(self):
        original = copy.deepcopy(self.base_doc)
        for mode in ("missing", "duplicate", "foreign", "warning", "unmapped", "unzone"):
            with self.subTest(mode=mode):
                self.base_doc = copy.deepcopy(original)
                group = self.base_doc.find("./" + NS + "ResultSummary/" + NS + "RunInfos")
                if mode == "missing": group.remove(group[0])
                elif mode == "duplicate": group.append(copy.deepcopy(group[0]))
                elif mode == "foreign": self.base_doc.append(copy.deepcopy(group[0]))
                elif mode == "warning": group[0].set("outcome", "Warning")
                elif mode == "unzone": group[0].set("timestamp", "2026-10-17T00:00:00.1234567")
                else: group[0].find("./" + NS + "Text").text = "[xUnit.net 00:00:00.10]     Foreign [FAIL]"
                with self.assertRaises(ValueError): self.check_baseline()

    def test_raw_coverage_missing_empty_or_divergent_refused(self):
        raw = self.candidate / "coverage.cobertura.xml"
        original = raw.read_bytes()
        raw.unlink()
        with self.assertRaises(ValueError): self.check_candidate()
        raw.write_text("<coverage/>", encoding="utf-8")
        with self.assertRaises(ValueError): self.check_candidate()
        raw.write_bytes(original)
        copies = self.candidate / "copy"
        copies.mkdir()
        (copies / raw.name).write_text("<coverage/>", encoding="utf-8")
        with self.assertRaises(ValueError): self.check_candidate()

    def test_dtd_or_duplicate_trx_refused(self):
        self.check_baseline()
        self.write(self.candidate, self.candidate_doc)
        path = self.candidate / "results.trx"
        original = path.read_bytes()
        path.write_bytes(b'<!DOCTYPE TestRun [<!ENTITY x "bad">]>' + original)
        with self.assertRaises(ValueError): guard.verify(self.candidate, self.manifest, "candidate", 0, self.baseline)
        path.write_bytes(original)
        (self.candidate / "copy.trx").write_bytes(original)
        with self.assertRaises(ValueError): guard.verify(self.candidate, self.manifest, "candidate", 0, self.baseline)

    def test_candidate_requires_actual_unchanged_baseline_proof(self):
        self.check_baseline()
        self.write(self.candidate, self.candidate_doc)
        proof = self.baseline / "file-metadata-binding-proof.json"
        retained = proof.read_bytes()
        proof.unlink()
        with self.assertRaises(FileNotFoundError): guard.verify(self.candidate, self.manifest, "candidate", 0, self.baseline)
        proof.write_bytes(retained)
        changed = json.loads(retained)
        changed["identities"][next(iter(changed["identities"]))] = str(uuid.uuid4())
        proof.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValueError): guard.verify(self.candidate, self.manifest, "candidate", 0, self.baseline)

    def test_observer_retains_exact_reviewed_ownership_implementation(self):
        scripts = pathlib.Path(__file__).parent
        original = (scripts / "observe-supplier-address-providers.py").read_text(encoding="utf-8")
        reviewed = original.replace(
            "'FullyQualifiedName~ProcurementSupplierAddressScalarStringTests'",
            "('FullyQualifiedName=Legacy.Maliev.ProcurementService.Tests.Integration.PurchaseOrderFileMetadataBindingTests.PrimitiveMembers_UsePublicTypedStringReader'\n"
            "                if phase == 'baseline' else 'FullyQualifiedName~PurchaseOrderFileMetadataBindingTests')")
        reviewed = reviewed.replace("'purpose':'Supplier address33 isolated phase'",
                                    "'purpose':'File metadata isolated16 baseline or108 candidate phase'")
        reviewed = reviewed.replace("def observe_disposal(owned, postgres, receipt):",
                                    OBSERVER_READ_HELPERS + "def observe_disposal(owned, postgres, receipt):")
        reviewed = reviewed.replace(
            "        logs = (output/'test-console.log').read_text(encoding='utf-8')\n"
            "        reports = list(output.rglob('*.trx'))\n"
            "        require(len(reports) == 1, 'Require actual filtered TRX for container ownership')\n"
            "        doc = ET.parse(reports[0])",
            "        logs, doc, trx_raw = read_phase_payload(output)")
        reviewed = reviewed.replace("hashlib.sha256(reports[0].read_bytes()).hexdigest()", "hashlib.sha256(trx_raw).hexdigest()")
        self.assertEqual(reviewed, (scripts / "observe-file-metadata-providers.py").read_text(encoding="utf-8"))

    def test_preserved_proof_is_never_overwritten(self):
        self.check_baseline()
        proof = self.baseline / "file-metadata-binding-proof.json"
        proof.write_text('{"retained":"different"}', encoding="utf-8")
        before = proof.read_bytes()
        with self.assertRaises(ValueError): self.check_baseline()
        self.assertEqual(before, proof.read_bytes())



class FileMetadataSourceReceiptControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.environment = mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "synthetic", "GITHUB_RUN_ATTEMPT": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def phase(self, phase="baseline"):
        directory = self.root / phase
        directory.mkdir(exist_ok=True)
        raw = b"<synthetic-not-runtime-evidence/>"
        (directory / "results.trx").write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        proof = {"phase": phase, "passed": 6 if phase == "baseline" else 108,
                 "failed": 10 if phase == "baseline" else 0, "skipped": 0, "trxSha256": sha}
        receipt = {"phase": phase, "exitCode": 1 if phase == "baseline" else 0,
                   "owningRun": "synthetic", "owningAttempt": "1", "processExited": True,
                   "normalFixtureDisposalProven": True, "resourcesAbsent": True,
                   "uncertainResourcesPreserved": False, "errors": [], "rawTrxSha256": sha,
                   "processSessionCleanup": {"verified": True, "forcedCleanup": False, "handlesClosed": True,
                                             "launcherExited": True, "remainingSessionMembers": [], "cleanupErrors": []},
                   "disposalObservation": {"settled": True, "errors": [], "polls": [
                       {"containerInventoryAvailable": True, "volumeInventoryAvailable": True,
                        "remainingContainerIds": [], "remainingVolumeNames": []}]}}
        (directory / "file-metadata-binding-proof.json").write_text(json.dumps(proof), encoding="utf-8")
        self.write_receipt(receipt, phase)
        return receipt

    def write_receipt(self, receipt, phase="baseline"):
        (self.root / phase / "provider-observation.json").write_text(json.dumps(receipt), encoding="utf-8")

    def test_both_phase_receipt_shapes_and_raw_hashes_pass(self):
        for phase in ("baseline", "candidate"):
            self.phase(phase)
            self.assertTrue(prep.require_phase_evidence(self.root, phase)["normalDisposal"])

    def test_forced_or_incomplete_process_cleanup_refused(self):
        original = self.phase()
        for key, bad in (("verified", False), ("forcedCleanup", True), ("handlesClosed", False),
                         ("launcherExited", False), ("remainingSessionMembers", [{"processId": 1}]),
                         ("cleanupErrors", ["uncertain"])):
            with self.subTest(key=key):
                receipt = copy.deepcopy(original)
                receipt["processSessionCleanup"][key] = bad
                self.write_receipt(receipt)
                with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")

    def test_custody_exit_or_disposal_flags_refused(self):
        original = self.phase()
        for key, bad in (("owningRun", "foreign"), ("owningAttempt", "2"), ("exitCode", 0), ("exitCode", True),
                         ("processExited", False), ("normalFixtureDisposalProven", False),
                         ("normalFixtureDisposalProven", "true"), ("resourcesAbsent", False),
                         ("uncertainResourcesPreserved", True), ("errors", ["uncertain"])):
            with self.subTest(key=key, bad=bad):
                receipt = copy.deepcopy(original)
                receipt[key] = bad
                self.write_receipt(receipt)
                with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")

    def test_unknown_terminal_inventory_or_changed_raw_trx_refused(self):
        original = self.phase()
        for key, bad in (("containerInventoryAvailable", False), ("volumeInventoryAvailable", False),
                         ("remainingContainerIds", ["uncertain"]), ("remainingVolumeNames", ["uncertain"])):
            with self.subTest(key=key):
                receipt = copy.deepcopy(original)
                receipt["disposalObservation"]["polls"][-1][key] = bad
                self.write_receipt(receipt)
                with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")
        self.write_receipt(original)
        (self.root / "baseline" / "results.trx").write_bytes(b"<changed/>")
        with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")



class FileMetadataBoundedReaderControls(unittest.TestCase):
    # Small temporary unit-test ceilings exercise max+1 arithmetic without large
    # allocations. Production ceilings and the machine admission floor are unchanged.
    setUp = FileMetadataSourceReceiptControls.setUp
    phase = FileMetadataSourceReceiptControls.phase
    write_receipt = FileMetadataSourceReceiptControls.write_receipt

    def result_fixture(self):
        fixture = FileMetadataResultControls("test_exact_namespace_summary_rosters_and_shared_ids_pass")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_all_readers_use_max_plus_one_and_actual_length_without_stat(self):
        for consumer in ("result", "source", "observer"):
            for length in (64, 65):
                with self.subTest(consumer=consumer, length=length):
                    requests = []

                    class TrackedStream(io.BytesIO):
                        def read(self, count=-1):
                            requests.append(count)
                            return super().read(count)

                    stream = TrackedStream(b"x" * length)
                    path = mock.Mock()
                    path.open.return_value = stream
                    path.stat.side_effect = AssertionError("stat is not a read bound")

                    def read():
                        if consumer == "result": return guard.read_bounded(path, 64)
                        if consumer == "source": return prep.read_bounded(path, 64, [64])
                        return observer.read_phase_file(path, 64, [64])

                    if length == 65:
                        with self.assertRaises(ValueError): read()
                    else:
                        self.assertEqual(b"x" * 64, read())
                    self.assertEqual([65], requests)
                    path.open.assert_called_once_with("rb")
                    path.stat.assert_not_called()
                    self.assertTrue(stream.closed)

    def test_oversize_trx_is_rejected_before_xml_parse(self):
        path = self.root / "oversize.trx"
        path.write_bytes(b"x" * 65)
        with mock.patch.object(guard, "MAX_TRX_BYTES", 64), mock.patch.object(guard.ET, "fromstring", side_effect=AssertionError("parsed oversized input")) as parser:
            with self.assertRaises(ValueError): guard.read_trx(path)
            parser.assert_not_called()

    def test_coverage_file_cap_rejects_before_coverage_parse(self):
        fixture = self.result_fixture()
        fixture.check_baseline()
        fixture.write(fixture.candidate, fixture.candidate_doc)
        raw = fixture.candidate / "coverage.cobertura.xml"
        raw.write_bytes(b"x" * 65)
        with mock.patch.object(guard, "MAX_COVERAGE_FILE_BYTES", 64), mock.patch.object(guard, "parse_xml", wraps=guard.parse_xml) as parser:
            with self.assertRaises(ValueError): guard.verify(fixture.candidate, fixture.manifest, "candidate", 0, fixture.baseline)
            self.assertEqual(1, parser.call_count)  # Only the bounded candidate TRX.

    def test_coverage_aggregate_and_file_count_are_bounded(self):
        fixture = self.result_fixture()
        fixture.check_baseline()
        fixture.write(fixture.candidate, fixture.candidate_doc)
        raw = (fixture.candidate / "coverage.cobertura.xml").read_bytes()
        for index in range(2):
            directory = fixture.candidate / ("copy" + str(index))
            directory.mkdir()
            (directory / "coverage.cobertura.xml").write_bytes(raw)
        with mock.patch.object(guard, "MAX_COVERAGE_TOTAL_BYTES", len(raw) * 2):
            with self.assertRaises(ValueError): guard.verify(fixture.candidate, fixture.manifest, "candidate", 0, fixture.baseline)
        for index in range(2, 4):
            directory = fixture.candidate / ("copy" + str(index))
            directory.mkdir()
            (directory / "coverage.cobertura.xml").write_bytes(raw)
        with self.assertRaises(ValueError): guard.verify(fixture.candidate, fixture.manifest, "candidate", 0, fixture.baseline)

    def test_xml_parsing_never_reopens_a_path(self):
        fixture = self.result_fixture()
        with mock.patch.object(guard.ET, "parse", side_effect=AssertionError("path reopened")):
            self.assertEqual(108, fixture.check_candidate()["passed"])

    def test_source_json_proof_and_receipt_caps_precede_parsing(self):
        for name in ("file-metadata-binding-proof.json", "provider-observation.json"):
            with self.subTest(name=name):
                self.phase()
                directory = self.root / "baseline"
                maximum = max(len(path.read_bytes()) for path in directory.glob("*.json")) + 10
                (directory / name).write_bytes(b"x" * (maximum + 1))
                with mock.patch.object(prep, "MAX_JSON_BYTES", maximum), mock.patch.object(prep.json, "loads", side_effect=AssertionError("parsed oversized JSON")) as parser:
                    with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")
                    parser.assert_not_called()

    def test_source_phase_aggregate_precedes_json_parsing(self):
        self.phase()
        total = sum(len(path.read_bytes()) for path in (self.root / "baseline").glob("*.json"))
        with mock.patch.object(prep.json, "loads", side_effect=AssertionError("parsed over-budget evidence")) as parser:
            with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline", [total - 1])
            parser.assert_not_called()

    def test_source_trx_cap_precedes_hashing(self):
        self.phase()
        (self.root / "baseline" / "results.trx").write_bytes(b"x" * 65)
        with mock.patch.object(prep, "MAX_TRX_BYTES", 64), mock.patch.object(prep.hashlib, "sha256", side_effect=AssertionError("hashed oversized input")) as hasher:
            with self.assertRaises(ValueError): prep.require_phase_evidence(self.root, "baseline")
            hasher.assert_not_called()

    def test_observer_log_and_trx_caps_precede_xml_parse(self):
        for oversize in ("log", "trx"):
            with self.subTest(oversize=oversize):
                output = self.root / ("observer-" + oversize)
                output.mkdir()
                (output / "test-console.log").write_bytes(b"x" * (65 if oversize == "log" else 1))
                (output / "results.trx").write_bytes(b"x" * (65 if oversize == "trx" else 1))
                with mock.patch.object(observer, "MAX_LOG_BYTES", 64), mock.patch.object(observer, "MAX_TRX_BYTES", 64), mock.patch.object(observer.ET, "fromstring", side_effect=AssertionError("parsed over-limit observer input")) as parser:
                    with self.assertRaises(ValueError): observer.read_phase_payload(output)
                    parser.assert_not_called()

    def test_observer_aggregate_and_report_enumeration_are_bounded(self):
        output = self.root / "observer-total"
        output.mkdir()
        log, trx = b"synthetic log", b"<TestRun/>"
        (output / "test-console.log").write_bytes(log)
        (output / "results.trx").write_bytes(trx)
        with mock.patch.object(observer, "MAX_PHASE_READ_BYTES", len(log) + len(trx) - 1), mock.patch.object(observer.ET, "fromstring", side_effect=AssertionError("parsed over-budget input")) as parser:
            with self.assertRaises(ValueError): observer.read_phase_payload(output)
            parser.assert_not_called()
        visited = []

        def reports():
            for index in range(3):
                visited.append(index)
                yield pathlib.Path(str(index) + ".trx")

        directory = mock.Mock()
        directory.rglob.return_value = reports()
        with self.assertRaises(ValueError): observer.phase_reports(directory)
        self.assertEqual([0, 1], visited)

    def test_result_json_cap_precedes_parsing(self):
        path = self.root / "oversize.json"
        path.write_bytes(b"x" * 65)
        with mock.patch.object(guard, "MAX_JSON_BYTES", 64), mock.patch.object(guard.json, "loads", side_effect=AssertionError("parsed oversized proof")) as parser:
            with self.assertRaises(ValueError): guard.read_json(path)
            parser.assert_not_called()


class MetadataRuntimeEnvelopeControls(unittest.TestCase):
    def test_exact_reviewed_four_input_envelope_passes(self):
        prep.require_runtime_roster(CONTRACT["implementationRuntime"])

    def test_each_missing_or_foreign_runtime_input_is_refused(self):
        original = CONTRACT["implementationRuntime"]
        for path in (*original, "Legacy.Maliev.ProcurementService.Data/Unreviewed.cs"):
            with self.subTest(path=path):
                changed = dict(original)
                if path in changed:
                    del changed[path]
                else:
                    changed[path] = "unreviewed"
                with self.assertRaises(ValueError):
                    prep.require_runtime_roster(changed)


if __name__ == "__main__":
    unittest.main()
