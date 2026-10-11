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
        ET.SubElement(self.document, "Counters", total="27", executed="27", passed="27", **counters)
        for index, case in enumerate(self.manifest["cases"]):
            execution = str(uuid.uuid5(uuid.NAMESPACE_OID, str(index)))
            definition = ET.SubElement(definitions, "UnitTest", id=case["id"], name=case["name"])
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(entries, "TestEntry", testId=case["id"], executionId=execution)
            ET.SubElement(results, "UnitTestResult", testId=case["id"], testName=case["name"], executionId=execution, outcome="Passed")
        (self.root / "coverage.cobertura.xml").write_text('<coverage><packages><package><classes><class><lines><line number="1" hits="1" /></lines></class></classes></package></packages></coverage>')

    def check(self):
        ET.ElementTree(self.document).write(self.root / "focused.trx")
        return focused.verify(self.root, self.manifest)

    def test_exact_roster_passes(self):
        self.assertEqual(27, self.check()["passed"])

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
                self.document.find("Counters").set(key, "1")
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


if __name__ == "__main__":
    unittest.main()
