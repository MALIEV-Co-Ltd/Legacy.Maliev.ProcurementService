"""Synthetic enrollment and source-binding controls only; no runtime/provider execution."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

REPOSITORY = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("procurement_health_gate", REPOSITORY / "scripts/verify-procurement-health-aliases.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def tag(name):
    return GATE.NAMESPACE + name


def fixture(root):
    source = root / "source"
    for name in GATE.SOURCE_PATHS:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPOSITORY / name).read_bytes())
    document = ET.Element(tag("TestRun"))
    definitions = ET.SubElement(document, tag("TestDefinitions"))
    entries = ET.SubElement(document, tag("TestEntries"))
    results = ET.SubElement(document, tag("Results"))
    for method in GATE.METHODS:
        identity = GATE.CLASS + "." + method
        test_id, execution_id = str(uuid.uuid4()), str(uuid.uuid4())
        unit = ET.SubElement(definitions, tag("UnitTest"), id=test_id, name=identity)
        ET.SubElement(unit, tag("Execution"), id=execution_id)
        ET.SubElement(unit, tag("TestMethod"), className=GATE.CLASS, name=method)
        ET.SubElement(entries, tag("TestEntry"), testId=test_id, executionId=execution_id)
        ET.SubElement(results, tag("UnitTestResult"), testName=identity, testId=test_id,
                      executionId=execution_id, outcome="Passed")
    summary = ET.SubElement(document, tag("ResultSummary"), outcome="Completed")
    counters = {"total": "5", "executed": "5", "passed": "5"}
    counters.update({name: "0" for name in ("failed", "error", "timeout", "aborted", "inconclusive",
        "passedButRunAborted", "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")})
    ET.SubElement(summary, tag("Counters"), **counters)
    coverage = ET.Element("coverage")
    package = ET.SubElement(ET.SubElement(coverage, "packages"), "package")
    cls = ET.SubElement(ET.SubElement(package, "classes"), "class")
    ET.SubElement(ET.SubElement(cls, "lines"), "line", number="1", hits="1")
    for name in ("raw-a", "raw-b"):
        directory = root / name
        directory.mkdir()
        ET.ElementTree(coverage).write(directory / "coverage.cobertura.xml", encoding="utf-8")
    return document, source


class ProcurementHealthEnrollmentControls(unittest.TestCase):
    def verify(self, root, document, source):
        ET.ElementTree(document).write(root / "synthetic.trx", encoding="utf-8")
        return GATE.verify(root, source)

    def test_exact_five_joined_synthetic_executions_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document, source = fixture(root)
            proof = self.verify(root, document, source)
            self.assertEqual(5, proof["passed"])
            self.assertEqual(5, len(proof["identities"]))
            self.assertTrue(proof["strictTrxJoins"])
            self.assertFalse(proof["fullServiceAcceptance"])
            self.assertFalse(proof["providerOrFinancialExecutionAcceptance"])

    def test_native_inventory_mutations_fail_closed(self):
        for mutation in ("missing", "extra", "failed", "skipped", "passing-error", "notice", "duplicate-execution",
                         "duplicate-definition", "entry-join", "wrong-class", "wrong-method", "wrong-name",
                         "zero-guid", "wrong-counter", "nested-counter", "coverage-drift", "doctype"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                document, source = fixture(root)
                definitions = document.find(tag("TestDefinitions"))
                entries = document.find(tag("TestEntries"))
                results = document.find(tag("Results"))
                summary = document.find(tag("ResultSummary"))
                if mutation == "missing":
                    results.remove(results[-1])
                elif mutation == "extra":
                    results.append(copy.deepcopy(results[0]))
                elif mutation in ("failed", "skipped"):
                    results[-1].set("outcome", "Failed" if mutation == "failed" else "NotExecuted")
                elif mutation == "passing-error":
                    ET.SubElement(ET.SubElement(results[-1], tag("Output")), tag("ErrorInfo"))
                elif mutation == "notice":
                    ET.SubElement(summary, tag("RunInfo"))
                elif mutation == "duplicate-execution":
                    results[-1].set("executionId", results[0].get("executionId"))
                elif mutation == "duplicate-definition":
                    definitions[-1].set("id", definitions[0].get("id"))
                elif mutation == "entry-join":
                    entries[-1].set("executionId", entries[0].get("executionId"))
                elif mutation in ("wrong-class", "wrong-method"):
                    definitions[-1].find(tag("TestMethod")).set("className" if mutation == "wrong-class" else "name", "Unreviewed")
                elif mutation == "wrong-name":
                    results[-1].set("testName", "Unreviewed")
                elif mutation == "zero-guid":
                    results[-1].set("executionId", str(uuid.UUID(int=0)))
                elif mutation == "wrong-counter":
                    summary.find(tag("Counters")).set("warning", "1")
                elif mutation == "nested-counter":
                    ET.SubElement(ET.SubElement(summary, tag("Output")), tag("Counters"))
                elif mutation == "coverage-drift":
                    (root / "raw-a/coverage.cobertura.xml").write_bytes(b"<coverage/>")
                if mutation == "doctype":
                    path = root / "synthetic.trx"
                    ET.ElementTree(document).write(path, encoding="utf-8")
                    path.write_bytes(b"<!DOCTYPE TestRun>" + path.read_bytes())
                    with self.assertRaises(ValueError):
                        GATE.verify(root, source)
                else:
                    with self.assertRaises(ValueError):
                        self.verify(root, document, source)

    def test_every_program_iam_controller_and_test_binding_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document, source = fixture(root)
            for name in GATE.SOURCE_PATHS:
                target = source / name
                original = target.read_bytes()
                target.write_bytes(original + b" ")
                with self.subTest(changed=name), self.assertRaises(ValueError):
                    self.verify(root, document, source)
                target.unlink()
                with self.subTest(missing=name), self.assertRaises(FileNotFoundError):
                    self.verify(root, document, source)
                target.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
