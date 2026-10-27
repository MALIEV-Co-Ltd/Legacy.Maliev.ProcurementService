"""Synthetic parser controls only; these fabricated GUIDs/names are never native evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("source_string_guard", Path(__file__).with_name("verify-procurement-string-boundaries.py"))
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
FROZEN = {
    "ProcurementRequiredAndLiteralSourceTests.FileJsonUpdatePreservesValidEmptyAndWhitespaceLiteralsWithoutCallingStorage": 2,
    "ProcurementRequiredAndLiteralSourceTests.SupplierSourceExplicitRequiredPropertiesAreRequiredInTheOwnedModel": 2,
    "ProcurementRequiredAndLiteralSourceTests.SupplierAddressCreateKeepsAllSpaceLiteralAndUpdateKeepsSourceValidEmptyAndZeroCountry": 1,
    "ProcurementRequiredAndLiteralSourceTests.BothOwnedDatabasesEnforceOriginalUtf16LengthWithoutTrimming": 4,
    "ProcurementSourceStringMigrationTests.InvalidRetainedRowsRejectMigrationWithoutChangingRowsSchemaOrHistory": 4,
    "ProcurementSourceStringMigrationTests.ValidRetainedLiteralsSurviveUpgradeRepeatAndRollback": 2,
    "ProcurementSourceStringMigrationTests.PostgreSqlUnicodeExpressionCountsSupplementaryScalarsAsTwoUtf16Units": 1,
}
BUCKET = {
    "ProcurementSourceStringMigrationTests.RetainedBucketOverflow_RefusesUpgradeWithoutChangingRowsSchemaOrHistory": 2,
    "ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses": 6,
    "ProcurementSourceStringMigrationTests.BucketBoundaryLockRefusal_PreservesRowsSchemaAndHistory": 2,
}
BUCKET_DISPLAYS = {
    "ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses": [
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"padding\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"empty\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"bmp50\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"mixed50\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"supplementary50\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketStorageBoundary_PreservesLiteralsAndRejectsDirectSqlBypasses(kind: \"padded\")"
    ],
    "ProcurementSourceStringMigrationTests.RetainedBucketOverflow_RefusesUpgradeWithoutChangingRowsSchemaOrHistory": [
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.RetainedBucketOverflow_RefusesUpgradeWithoutChangingRowsSchemaOrHistory(supplementaryCount: 26, suffix: \"\")",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.RetainedBucketOverflow_RefusesUpgradeWithoutChangingRowsSchemaOrHistory(supplementaryCount: 25, suffix: \"ก\")"
    ],
    "ProcurementSourceStringMigrationTests.BucketBoundaryLockRefusal_PreservesRowsSchemaAndHistory": [
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketBoundaryLockRefusal_PreservesRowsSchemaAndHistory(downgrade: False)",
        "Legacy.Maliev.ProcurementService.Tests.Data.ProcurementSourceStringMigrationTests.BucketBoundaryLockRefusal_PreservesRowsSchemaAndHistory(downgrade: True)"
    ]
}
REFERENCE = dict(FROZEN, **BUCKET)
NAMESPACE = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def fixture(roster=None):
    roster = REFERENCE if roster is None else roster
    root = ET.Element(NAMESPACE + "TestRun")
    results = ET.SubElement(root, NAMESPACE + "Results")
    definitions = ET.SubElement(root, NAMESPACE + "TestDefinitions")
    number = 0
    for method, count in roster.items():
        class_name, name = method.split(".")
        area = "Data" if class_name == "ProcurementSourceStringMigrationTests" else "Integration"
        class_name = "Legacy.Maliev.ProcurementService.Tests." + area + "." + class_name
        for ordinal in range(count):
            number += 1
            test_id = "00000000-0000-0000-0000-" + format(number, "012d")
            execution = "00000000-0000-0000-0001-" + format(number, "012d")
            display = (BUCKET_DISPLAYS[method][ordinal % len(BUCKET_DISPLAYS[method])] if method in BUCKET_DISPLAYS
                       else class_name + "." + name + "(synthetic: " + str(ordinal) + ")")
            definition = ET.SubElement(definitions, NAMESPACE + "UnitTest", {"id": test_id, "name": display})
            ET.SubElement(definition, NAMESPACE + "Execution", {"id": execution})
            ET.SubElement(definition, NAMESPACE + "TestMethod", {"className": class_name, "name": name})
            ET.SubElement(results, NAMESPACE + "UnitTestResult",
                          {"testId": test_id, "executionId": execution, "testName": display, "outcome": "Passed"})
    summary = ET.SubElement(root, NAMESPACE + "ResultSummary", {"outcome": "Completed"})
    counters = {name: "0" for name in (
        "total", "executed", "passed", "failed", "error", "timeout", "aborted", "inconclusive",
        "passedButRunAborted", "notRunnable", "notExecuted", "disconnected", "warning", "completed",
        "inProgress", "pending")}
    counters.update(total=str(number), executed=str(number), passed=str(number))
    ET.SubElement(summary, NAMESPACE + "Counters", counters)
    return root


class SourceStringRosterControls(unittest.TestCase):
    def test_exact_roster_keeps_all_original_methods_and_adds_only_ten_bucket_rows(self):
        self.assertEqual(16, sum(FROZEN.values()))
        self.assertEqual(10, sum(BUCKET.values()))
        self.assertEqual(REFERENCE, guard.EXPECTED)
        self.assertEqual(REFERENCE, guard.verify_trx(fixture()))

    def test_old_sixteen_case_run_is_not_accepted_as_current(self):
        with self.assertRaises(ValueError):
            guard.verify_trx(fixture(FROZEN))

    def test_each_original_or_new_missing_method_is_rejected(self):
        for omitted in REFERENCE:
            roster = {name: count for name, count in REFERENCE.items() if name != omitted}
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                guard.verify_trx(fixture(roster))

    def test_every_original_or_new_wrong_row_count_is_rejected(self):
        for method, count in REFERENCE.items():
            for difference in (-1, 1):
                roster = dict(REFERENCE)
                roster[method] = count + difference
                with self.subTest(method=method, difference=difference), self.assertRaises(ValueError):
                    guard.verify_trx(fixture(roster))

    def test_wrong_bucket_argument_cannot_replace_an_exact_native_theory_case(self):
        for method in BUCKET:
            root = fixture()
            definition = next(node for node in root.findall("./t:TestDefinitions/t:UnitTest", guard.NS)
                              if node.find("t:TestMethod", guard.NS).get("name") == method.split(".")[1])
            wrong = definition.get("name") + " synthetic unreviewed argument"
            definition.set("name", wrong)
            result = next(node for node in root.findall("./t:Results/t:UnitTestResult", guard.NS)
                          if node.get("testId") == definition.get("id"))
            result.set("testName", wrong)
            with self.subTest(method=method), self.assertRaises(ValueError):
                guard.verify_trx(root)

    def test_unknown_method_cannot_replace_known_case(self):
        root = fixture()
        method = root.find("./t:TestDefinitions/t:UnitTest/t:TestMethod", guard.NS)
        method.set("name", "UnreviewedSyntheticMethod")
        with self.assertRaises(ValueError):
            guard.verify_trx(root)

    def test_mismatched_result_display_or_definition_execution_is_rejected(self):
        for field in ("testName", "executionId"):
            root = fixture()
            result = root.find("./t:Results/t:UnitTestResult", guard.NS)
            result.set(field, "synthetic mismatch" if field == "testName" else "00000000-0000-0000-0002-000000000001")
            with self.subTest(field=field), self.assertRaises(ValueError):
                guard.verify_trx(root)

    def test_duplicate_definition_result_or_native_container_is_rejected(self):
        for path in ("./t:TestDefinitions/t:UnitTest", "./t:Results/t:UnitTestResult", "./t:Results"):
            root = fixture()
            child = root.find(path, guard.NS)
            parent = root if path == "./t:Results" else root.find(path.rsplit("/", 1)[0], guard.NS)
            parent.append(copy.deepcopy(child))
            with self.subTest(path=path), self.assertRaises(ValueError):
                guard.verify_trx(root)

    def test_nonpassing_case_is_rejected_even_with_passing_counters(self):
        for outcome in ("Failed", "NotExecuted", "NotRunnable", ""):
            root = fixture()
            root.find("./t:Results/t:UnitTestResult", guard.NS).set("outcome", outcome)
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                guard.verify_trx(root)

    def test_old_incomplete_failure_or_extra_counters_are_rejected(self):
        for name, value in (("total", "16"), ("executed", "25"), ("passed", "25"),
                            ("failed", "1"), ("notExecuted", "1"), ("foreign", "0")):
            root = fixture()
            root.find("./t:ResultSummary/t:Counters", guard.NS).set(name, value)
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                guard.verify_trx(root)

    def test_missing_counter_or_incomplete_summary_is_rejected(self):
        root = fixture()
        del root.find("./t:ResultSummary/t:Counters", guard.NS).attrib["passed"]
        with self.assertRaises(ValueError):
            guard.verify_trx(root)
        root = fixture()
        root.find("./t:ResultSummary", guard.NS).set("outcome", "Aborted")
        with self.assertRaises(ValueError):
            guard.verify_trx(root)


if __name__ == "__main__":
    unittest.main()
