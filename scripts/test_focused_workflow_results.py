"""Negative controls for the hosted focused-result acceptance boundary."""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("focused", pathlib.Path(__file__).with_name("verify-focused-workflow-results.py"))
focused = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focused)


class FocusedWorkflowResultsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name)
        self.manifest = json.loads(pathlib.Path("docs/procurement-focused-workflow-contract.json").read_text())
        self.document = ET.Element("TestRun")
        definitions = ET.SubElement(self.document, "TestDefinitions")
        entries = ET.SubElement(self.document, "TestEntries")
        results = ET.SubElement(self.document, "Results")
        counters = {k: "0" for k in ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
                                    "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")}
        summary = ET.SubElement(self.document, "ResultSummary", outcome="Completed")
        ET.SubElement(summary, "Counters", total="28", executed="28", passed="28", **counters)
        for index, case in enumerate(self.manifest["cases"]):
            execution = str(uuid.uuid5(uuid.NAMESPACE_OID, str(index)))
            definition = ET.SubElement(definitions, "UnitTest", id=case["id"], name=case["name"])
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(entries, "TestEntry", testId=case["id"], executionId=execution)
            ET.SubElement(results, "UnitTestResult", testId=case["id"], testName=case["name"], executionId=execution, outcome="Passed")
        (self.root / "coverage.cobertura.xml").write_text('<coverage><packages><package><classes><class><lines><line number="1" hits="1" /></lines></class></classes></package></packages></coverage>')

    def check(self):
        namespaced = copy.deepcopy(self.document)
        for node in namespaced.iter():
            if not node.tag.startswith("{"):
                node.tag = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}" + node.tag
        ET.ElementTree(namespaced).write(self.root / "focused.trx")
        return focused.verify(self.root, self.manifest)

    def test_exact_roster_passes(self):
        self.assertEqual(28, self.check()["passed"])

    def test_rejects_result_boundary_drift(self):
        original = copy.deepcopy(self.document)
        for attribute, value in [("testName", "foreign"), ("testId", "foreign"), ("executionId", "foreign"), ("outcome", "NotExecuted")]:
            with self.subTest(attribute=attribute):
                self.document = copy.deepcopy(original)
                self.document.find("./Results/UnitTestResult").set(attribute, value)
                with self.assertRaises(ValueError): self.check()

    def test_rejects_malformed_execution_guid(self):
        original = copy.deepcopy(self.document)
        for invalid in ["", "0", "not-a-guid", "6DA217E6FA464DC2A3E9E0C0A60C9935", "6DA217E6-FA46-4DC2-A3E9-E0C0A60C9935"]:
            with self.subTest(invalid=invalid):
                self.document = copy.deepcopy(original)
                result = self.document.find("./Results/UnitTestResult")
                result.set("executionId", invalid)
                self.document.find("./TestDefinitions/UnitTest/Execution").set("id", invalid)
                self.document.find("./TestEntries/TestEntry").set("executionId", invalid)
                with self.assertRaises(ValueError): self.check()

    def test_rejects_duplicate_execution(self):
        results = self.document.find("./Results")
        results[1].set("executionId", results[0].get("executionId"))
        with self.assertRaises(ValueError): self.check()

    def test_rejects_missing_definition_or_entry(self):
        original = copy.deepcopy(self.document)
        for container in ["TestDefinitions", "TestEntries", "Results"]:
            with self.subTest(container=container):
                self.document = copy.deepcopy(original)
                parent = self.document.find(container)
                parent.remove(parent[0])
                with self.assertRaises(ValueError): self.check()

    def test_rejects_counter_or_error_drift(self):
        original = copy.deepcopy(self.document)
        for key in ["total", "executed", "passed", "failed", "error", "timeout", "aborted", "inconclusive",
                    "passedButRunAborted", "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending"]:
            with self.subTest(key=key):
                self.document = copy.deepcopy(original)
                self.document.find("./ResultSummary/Counters").set(key, "1")
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        ET.SubElement(self.document, "ErrorInfo")
        with self.assertRaises(ValueError): self.check()

    def test_rejects_missing_or_divergent_raw_coverage(self):
        raw = self.root / "coverage.cobertura.xml"
        original = raw.read_bytes()
        raw.unlink()
        with self.assertRaises(ValueError): self.check()
        raw.write_text('<coverage/>')
        with self.assertRaises(ValueError): self.check()
        raw.write_bytes(original)
        copies = self.root / "copy"
        copies.mkdir()
        (copies / raw.name).write_text("<coverage/>")
        with self.assertRaises(ValueError): self.check()

    def test_rejects_declared_identity_drift(self):
        self.manifest["cases"][0]["name"] = "foreign"
        with self.assertRaises(ValueError): self.check()


    def test_rejects_each_missing_case_including_structural_self_check(self):
        original = copy.deepcopy(self.document)
        for case in self.manifest["cases"]:
            with self.subTest(name=case["name"]):
                self.document = copy.deepcopy(original)
                for container in ["TestDefinitions", "TestEntries", "Results"]:
                    parent = self.document.find(container)
                    identity_key = "id" if container == "TestDefinitions" else "testId"
                    row = next(row for row in parent if row.get(identity_key) == case["id"])
                    parent.remove(row)
                self.document.find("./ResultSummary/Counters").set("total", "27")
                self.document.find("./ResultSummary/Counters").set("executed", "27")
                self.document.find("./ResultSummary/Counters").set("passed", "27")
                with self.assertRaises(ValueError): self.check()

    def test_rejects_extra_case_even_with_consistent_joins(self):
        identity, execution = str(uuid.uuid4()), str(uuid.uuid4())
        definition = ET.SubElement(self.document.find("TestDefinitions"), "UnitTest", id=identity, name="foreign")
        ET.SubElement(definition, "Execution", id=execution)
        ET.SubElement(self.document.find("TestEntries"), "TestEntry", testId=identity, executionId=execution)
        ET.SubElement(self.document.find("Results"), "UnitTestResult", testId=identity, testName="foreign",
                      executionId=execution, outcome="Passed")
        for key in ["total", "executed", "passed"]:
            self.document.find("./ResultSummary/Counters").set(key, "29")
        with self.assertRaises(ValueError): self.check()



    def test_rejects_nested_or_duplicate_summary_and_counters(self):
        original = copy.deepcopy(self.document)
        for tag in ["ResultSummary", "Counters"]:
            for nested in [False, True]:
                with self.subTest(tag=tag, nested=nested):
                    self.document = copy.deepcopy(original)
                    existing = self.document.find(".//" + tag)
                    parent = ET.SubElement(self.document, "Output") if nested else self.document
                    clone = copy.deepcopy(existing)
                    if tag == "ResultSummary":
                        clone.set("outcome", "Failed")
                    else:
                        clone.set("failed", "1")
                    parent.append(clone)
                    with self.assertRaises(ValueError): self.check()

    def test_rejects_relocated_required_summary_or_counters(self):
        original = copy.deepcopy(self.document)
        for tag in ["ResultSummary", "Counters"]:
            with self.subTest(tag=tag):
                self.document = copy.deepcopy(original)
                parent = self.document if tag == "ResultSummary" else self.document.find("ResultSummary")
                row = parent.find(tag)
                parent.remove(row)
                ET.SubElement(parent, "Output").append(row)
                with self.assertRaises(ValueError): self.check()

    def test_rejects_adverse_summary_or_run_info(self):
        original = copy.deepcopy(self.document)
        for outcome in ["Failed", "Error", "Aborted", "InProgress", "Warning", ""]:
            with self.subTest(summary_outcome=outcome):
                self.document = copy.deepcopy(original)
                self.document.find("ResultSummary").set("outcome", outcome)
                with self.assertRaises(ValueError): self.check()
        for nested in [False, True]:
            for outcome in ["Error", "Warning", "Failed", "Aborted", "NotExecuted", ""]:
                with self.subTest(run_info_outcome=outcome, nested=nested):
                    self.document = copy.deepcopy(original)
                    parent = self.document if nested else self.document.find("ResultSummary")
                    notice = ET.SubElement(ET.SubElement(parent, "RunInfos"), "RunInfo", outcome=outcome)
                    ET.SubElement(notice, "Text").text = "runner failure"
                    with self.assertRaises(ValueError): self.check()

    def test_rejects_missing_or_unknown_counter(self):
        original = copy.deepcopy(self.document)
        for key in list(original.find("./ResultSummary/Counters").attrib):
            with self.subTest(missing_counter=key):
                self.document = copy.deepcopy(original)
                del self.document.find("./ResultSummary/Counters").attrib[key]
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        self.document.find("./ResultSummary/Counters").set("foreign", "0")
        with self.assertRaises(ValueError): self.check()

    def test_rejects_wrong_or_missing_namespace(self):
        for namespace in ["", "{urn:foreign}"]:
            with self.subTest(namespace=namespace):
                document = copy.deepcopy(self.document)
                for node in document.iter():
                    node.tag = namespace + node.tag
                ET.ElementTree(document).write(self.root / "focused.trx")
                with self.assertRaises(ValueError): focused.verify(self.root, self.manifest)

    def test_rejects_mixed_namespace_or_duplicate_result_containers(self):
        original = copy.deepcopy(self.document)
        for tag in ["TestDefinitions", "TestEntries", "Results"]:
            with self.subTest(duplicate=tag):
                self.document = copy.deepcopy(original)
                self.document.append(copy.deepcopy(self.document.find(tag)))
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        self.document.find("Results")[0].tag = "{urn:foreign}UnitTestResult"
        with self.assertRaises(ValueError): self.check()

    def test_rejects_nested_rows_and_duplicate_definition_execution(self):
        original = copy.deepcopy(self.document)
        for container in ["TestDefinitions", "TestEntries", "Results"]:
            with self.subTest(container=container):
                self.document = copy.deepcopy(original)
                parent = self.document.find(container)
                row = parent[0]
                parent.remove(row)
                ET.SubElement(parent, "Output").append(row)
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        definition = self.document.find("./TestDefinitions/UnitTest")
        definition.append(copy.deepcopy(definition.find("Execution")))
        with self.assertRaises(ValueError): self.check()


if __name__ == "__main__":
    unittest.main()
