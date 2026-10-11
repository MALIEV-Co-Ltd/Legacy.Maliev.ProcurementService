"""Fake TRX acceptance controls; these are not native journal executions."""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("owner_correlation", pathlib.Path(__file__).with_name("verify-owner-correlation-results.py"))
owner_correlation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner_correlation)


class OwnerCorrelationResultsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.manifest = json.loads(pathlib.Path("docs/procurement-owner-correlation-contract.json").read_text(encoding="utf-8"))
        self.document = ET.Element("TestRun", id=str(uuid.uuid4()))
        summary = ET.SubElement(self.document, "ResultSummary", outcome="Completed")
        counters = {key: "0" for key in ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
                    "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")}
        ET.SubElement(summary, "Counters", total="23", executed="23", passed="23", **counters)
        definitions = ET.SubElement(self.document, "TestDefinitions")
        entries = ET.SubElement(self.document, "TestEntries")
        results = ET.SubElement(self.document, "Results")
        for method in self.manifest["methods"]:
            test_id, execution = str(uuid.uuid4()), str(uuid.uuid4())
            name = self.manifest["className"] + "." + method
            definition = ET.SubElement(definitions, "UnitTest", id=test_id, name=name)
            ET.SubElement(definition, "Execution", id=execution)
            ET.SubElement(definition, "TestMethod", className=self.manifest["className"], name=method,
                          codeBase="/owned/bin/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll")
            ET.SubElement(entries, "TestEntry", testId=test_id, executionId=execution)
            ET.SubElement(results, "UnitTestResult", testId=test_id, executionId=execution, testName=name, outcome="Passed")

    def check(self):
        ET.ElementTree(self.document).write(self.root / "owner_correlation.trx")
        return owner_correlation.verify(self.root, self.manifest)

    def test_exact_roster(self):
        self.assertEqual(23, self.check()["passed"])

    def test_missing_duplicate_or_extra_roster(self):
        original = copy.deepcopy(self.manifest)
        for methods in [original["methods"][:-1], original["methods"] + ["extra"], [original["methods"][0]] * 23]:
            with self.subTest(methods=methods):
                self.manifest = copy.deepcopy(original)
                self.manifest["methods"] = methods
                with self.assertRaises(ValueError): self.check()

    def test_result_and_join_drift(self):
        original = copy.deepcopy(self.document)
        changes = [("./Results/UnitTestResult", "outcome", "NotExecuted"),
                   ("./Results/UnitTestResult", "testName", "foreign"),
                   ("./Results/UnitTestResult", "testId", str(uuid.uuid4())),
                   ("./TestEntries/TestEntry", "executionId", str(uuid.uuid4())),
                   ("./TestDefinitions/UnitTest/Execution", "id", str(uuid.uuid4())),
                   ("./TestDefinitions/UnitTest/TestMethod", "name", "foreign"),
                   ("./TestDefinitions/UnitTest/TestMethod", "className", "foreign"),
                   ("./TestDefinitions/UnitTest/TestMethod", "codeBase", "/Debug/net10.0/Legacy.Maliev.ProcurementService.Tests.dll")]
        for path, key, value in changes:
            with self.subTest(path=path, key=key):
                self.document = copy.deepcopy(original)
                self.document.find(path).set(key, value)
                with self.assertRaises(ValueError): self.check()

    def test_every_counter(self):
        original = copy.deepcopy(self.document)
        for key in original.find("./ResultSummary/Counters").attrib:
            with self.subTest(key=key):
                self.document = copy.deepcopy(original)
                self.document.find("./ResultSummary/Counters").set(key, "1")
                with self.assertRaises(ValueError): self.check()

    def test_summary_run_info_error_and_cardinality(self):
        original = copy.deepcopy(self.document)
        for tag in ["ErrorInfo", "RunInfo", "ResultSummary"]:
            with self.subTest(tag=tag):
                self.document = copy.deepcopy(original)
                ET.SubElement(self.document, tag)
                with self.assertRaises(ValueError): self.check()
        for tag in ["Results", "TestDefinitions", "TestEntries"]:
            with self.subTest(tag=tag):
                self.document = copy.deepcopy(original)
                parent = self.document.find(tag)
                parent.remove(parent[0])
                with self.assertRaises(ValueError): self.check()

    def test_noncanonical_and_duplicate_guid(self):
        original = copy.deepcopy(self.document)
        for value in ["", "invalid", str(uuid.uuid4()).upper()]:
            with self.subTest(value=value):
                self.document = copy.deepcopy(original)
                self.document.find("./Results/UnitTestResult").set("testId", value)
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        self.document.find("Results")[1].set("executionId", self.document.find("Results")[0].get("executionId"))
        with self.assertRaises(ValueError): self.check()

    def test_requires_one_report(self):
        self.check()
        (self.root / "extra.trx").write_bytes((self.root / "owner_correlation.trx").read_bytes())
        with self.assertRaises(ValueError): self.check()

    def test_rejects_foreign_root_nested_failure_and_duplicate_structures(self):
        original = copy.deepcopy(self.document)
        for tag in ["ResultSummary", "Counters", "TestDefinitions", "TestEntries", "Results",
                    "UnitTest", "TestEntry", "UnitTestResult", "TestMethod", "Execution", "TestRun"]:
            with self.subTest(nested=tag):
                self.document = copy.deepcopy(original)
                wrapper = ET.SubElement(self.document, "Wrapper")
                ET.SubElement(wrapper, tag, outcome="Failed")
                with self.assertRaises(ValueError): self.check()
        for tag in ["TestDefinitions", "TestEntries", "Results"]:
            with self.subTest(duplicate=tag):
                self.document = copy.deepcopy(original)
                ET.SubElement(self.document, tag)
                with self.assertRaises(ValueError): self.check()
        for tag in ["TestMethod", "Execution"]:
            with self.subTest(definition=tag):
                self.document = copy.deepcopy(original)
                definition = self.document.find("./TestDefinitions/UnitTest")
                wrapper = ET.SubElement(definition, "Wrapper")
                wrapper.append(copy.deepcopy(definition.find(tag)))
                with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        self.document.tag = "ForeignRoot"
        with self.assertRaises(ValueError): self.check()
        self.document = copy.deepcopy(original)
        wrapper = ET.SubElement(self.document, "Wrapper")
        summary = ET.SubElement(wrapper, "ResultSummary", outcome="Failed")
        ET.SubElement(summary, "Counters", failed="1")
        results = ET.SubElement(wrapper, "Results")
        ET.SubElement(results, "UnitTestResult", outcome="Failed")
        with self.assertRaises(ValueError): self.check()


    def test_exact_authored_roster_and_root_guid_are_frozen(self):
        original = copy.deepcopy(self.manifest)
        self.manifest["methods"][0] = "UnreviewedMethod"
        with self.assertRaises(ValueError): self.check()
        self.manifest = original
        for value in ["", "invalid", str(uuid.uuid4()).upper()]:
            with self.subTest(value=value):
                self.document.set("id", value)
                with self.assertRaises(ValueError): self.check()


if __name__ == "__main__":
    unittest.main()
