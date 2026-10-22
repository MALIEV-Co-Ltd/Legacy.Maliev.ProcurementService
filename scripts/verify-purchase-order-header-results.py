#!/usr/bin/env python3
"""Verify the actual focused purchase-order-header TRX without disclosing test data."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


TEST_CLASS = (
    "Legacy.Maliev.ProcurementService.Tests.Integration."
    "ProcurementPurchaseOrderHeaderBindingTests"
)
METHOD_CASES = {
    "AllTextFields_MatchPinnedPublicTypedReader": 9,
    "AllReferenceFields_MatchPinnedPublicTypedReader": 8,
    "EveryRecognizedField_RejectsObjectsAndArrays": 34,
    "EveryReference_RejectsBooleanFractionAndOverflow": 12,
    "AllFields_DuplicateAssignmentsAreOrderedAndTypedNullsAreSkipped": 3,
    "EveryMalformedOccurrence_RejectsEvenWhenAnotherDuplicateIsValid": 34,
    "FreshOmittedOrExplicitNullFields_DefaultToNull": 2,
    "HttpNumericText_PreservesDistinctContactsAndAllHeaderFields": 2,
    "HttpBooleanText_PersistsLowercaseStrings": 4,
    "HttpOmissionAndNull_ClearNullableHeaderProjection": 4,
    "HttpMalformedRecognizedField_RefusesBeforeWrites": 4,
    "HttpDuplicateNull_DoesNotEraseEarlierAssignment": 4,
    "HttpBadFirstDuplicate_CannotBeHidden": 4,
    "HttpAnonymousOrWrongPermission_CannotWrite": 4,
    "HttpWrongRoot_IsBadRequestWithoutWrites": 4,
    "Converter_IsMvcRequestOnly_PreservesWriteShapeAndSkipsUnknownGraphs": 1,
    "PropertyLookup_MatchesPinnedPublicOrdinalComparer": 2,
}
EXPECTED_CASES = 135
COUNTER_KEYS = {
    "total", "executed", "passed", "failed", "error", "timeout", "aborted",
    "inconclusive", "passedButRunAborted", "notRunnable", "notExecuted",
    "disconnected", "warning", "completed", "inProgress", "pending",
}
MAX_TRX_FILES = 16
MAX_TRX_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class VerificationError(ValueError):
    """Carries only a fixed diagnostic code, never source text."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationError(code)


def one(parent: ET.Element, path: str, code: str) -> ET.Element:
    matches = parent.findall(path)
    require(len(matches) == 1, code)
    return matches[0]


def opaque_id(value: str | None, code: str) -> str:
    require(value is not None and bool(value) and value == value.strip(), code)
    return value


def read_reports(directory: Path) -> list[ET.Element]:
    require(directory.is_dir() and not directory.is_symlink(), "directory_invalid")
    paths = sorted(directory.rglob("*.trx"))
    require(1 <= len(paths) <= MAX_TRX_FILES, "trx_file_count")
    documents = []
    total_bytes = 0
    for path in paths:
        require(path.is_file() and not path.is_symlink(), "trx_file_invalid")
        current = path.parent
        while current != directory:
            require(not current.is_symlink(), "trx_path_symlink")
            current = current.parent
        with path.open("rb") as stream:
            source = stream.read(MAX_TRX_BYTES + 1)
        total_bytes += len(source)
        require(0 < len(source) <= MAX_TRX_BYTES and
                total_bytes <= MAX_TOTAL_BYTES and
                path.stat().st_size == len(source), "trx_size_limit")
        try:
            text = source.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as error:
            raise VerificationError("trx_unsupported_encoding") from error
        require("\x00" not in text, "trx_unsupported_encoding")
        declaration = re.match(r"\A<\?xml\s+([^?]*)\?>", text)
        if declaration is not None:
            encoding = re.search(r"\bencoding\s*=\s*(['\"])(.*?)\1",
                                 declaration.group(1), re.IGNORECASE)
            require(encoding is None or encoding.group(2).lower() == "utf-8",
                    "trx_unsupported_encoding")
        require(re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE) is None,
                "trx_unsupported_xml")
        try:
            document = ET.fromstring(source)
        except ET.ParseError as error:
            raise VerificationError("trx_malformed_xml") from error
        require(document.tag.split("}")[-1] == "TestRun", "trx_root")
        documents.append(document)
    return documents


def verify(directory: Path) -> dict[str, int | bool]:
    require(len(METHOD_CASES) == 17 and sum(METHOD_CASES.values()) == EXPECTED_CASES,
            "frozen_roster_invalid")
    documents = read_reports(directory)
    all_test_ids: set[str] = set()
    all_execution_ids: set[str] = set()
    method_counts: Counter[str] = Counter()
    total_results = 0

    for document in documents:
        definitions_node = one(document, "./{*}TestDefinitions", "definitions_collection")
        entries_node = one(document, "./{*}TestEntries", "entries_collection")
        results_node = one(document, "./{*}Results", "results_collection")
        summary = one(document, "./{*}ResultSummary", "summary_collection")
        require(len(document.findall(".//{*}ResultSummary")) == 1,
                "summary_collection")
        require(summary.get("outcome") in {"Completed", "Passed"}, "summary_outcome")
        require(not document.findall(".//{*}RunInfo") and
                not document.findall(".//{*}ErrorInfo"), "nonpassing_evidence")

        definitions = definitions_node.findall("./{*}UnitTest")
        entries = entries_node.findall("./{*}TestEntry")
        results = results_node.findall("./{*}UnitTestResult")
        count = len(results)
        require(count > 0 and len(definitions) == len(entries) == count,
                "trx_collection_counts")
        require(len(definitions_node) == len(definitions) and
                len(entries_node) == len(entries) and
                len(results_node) == len(results), "foreign_collection_row")
        require(len(document.findall(".//{*}UnitTest")) == count and
                len(document.findall(".//{*}TestEntry")) == count and
                len(document.findall(".//{*}UnitTestResult")) == count,
                "trx_extra_rows")
        counters = one(summary, "./{*}Counters", "counters_collection")
        require(len(document.findall(".//{*}Counters")) == 1,
                "counters_collection")
        require(set(counters.attrib) == COUNTER_KEYS, "counter_keys")
        for key in COUNTER_KEYS:
            value = counters.get(key)
            require(value is not None and re.fullmatch(r"[0-9]+", value) is not None,
                    "counter_numeric")
            expected = count if key in {"total", "executed", "passed"} else 0
            require(int(value) == expected, "counter_value")

        definitions_by_id: dict[str, ET.Element] = {}
        for definition in definitions:
            test_id = opaque_id(definition.get("id"), "definition_id")
            require(test_id not in definitions_by_id and test_id not in all_test_ids,
                    "duplicate_test_id")
            definitions_by_id[test_id] = definition
            all_test_ids.add(test_id)
        entries_by_id: dict[str, ET.Element] = {}
        local_execution_ids: set[str] = set()
        for entry in entries:
            test_id = opaque_id(entry.get("testId"), "entry_test_id")
            execution_id = opaque_id(entry.get("executionId"), "entry_execution_id")
            require(test_id not in entries_by_id, "duplicate_entry")
            require(execution_id not in local_execution_ids and
                    execution_id not in all_execution_ids, "duplicate_execution_id")
            entries_by_id[test_id] = entry
            local_execution_ids.add(execution_id)
            all_execution_ids.add(execution_id)
        require(set(definitions_by_id) == set(entries_by_id), "definition_entry_join")

        seen_results: set[str] = set()
        for result in results:
            test_id = opaque_id(result.get("testId"), "result_test_id")
            execution_id = opaque_id(result.get("executionId"), "result_execution_id")
            name = result.get("testName")
            require(test_id not in seen_results, "duplicate_result")
            seen_results.add(test_id)
            require(test_id in definitions_by_id and test_id in entries_by_id,
                    "unbound_result")
            definition = definitions_by_id[test_id]
            entry = entries_by_id[test_id]
            require(name is not None and bool(name) and
                    definition.get("name") == name, "result_definition_name")
            defined_execution = one(definition, "./{*}Execution",
                                    "definition_execution")
            require(execution_id == defined_execution.get("id") ==
                    entry.get("executionId"), "execution_join")
            require(result.get("outcome") == "Passed", "result_outcome")
            method = one(definition, "./{*}TestMethod", "test_method")
            class_name = (method.get("className") or "").split(",", 1)[0].strip()
            method_name = method.get("name") or ""
            require(class_name == TEST_CLASS, "foreign_test_class")
            require(method_name in METHOD_CASES, "foreign_test_method")
            method_counts[method_name] += 1
        require(seen_results == set(definitions_by_id), "result_roster_join")
        total_results += count

    require(total_results == EXPECTED_CASES and
            len(all_test_ids) == len(all_execution_ids) == EXPECTED_CASES,
            "total_case_count")
    require(dict(method_counts) == METHOD_CASES, "method_case_counts")
    return {
        "trx_files": len(documents),
        "methods": len(METHOD_CASES),
        "definitions": EXPECTED_CASES,
        "entries": EXPECTED_CASES,
        "passed": EXPECTED_CASES,
        "failed": 0,
        "strict_three_way_join": True,
    }


def _synthetic_cases() -> list[str]:
    return [method for method, count in METHOD_CASES.items() for _ in range(count)]


def _synthetic_document(methods: list[str], start: int = 0) -> ET.Element:
    namespace = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"
    def tag(name: str) -> str:
        return "{" + namespace + "}" + name

    root = ET.Element(tag("TestRun"))
    definitions = ET.SubElement(root, tag("TestDefinitions"))
    entries = ET.SubElement(root, tag("TestEntries"))
    results = ET.SubElement(root, tag("Results"))
    summary = ET.SubElement(root, tag("ResultSummary"), outcome="Completed")
    counters = {key: str(len(methods) if key in {"total", "executed", "passed"} else 0)
                for key in COUNTER_KEYS}
    ET.SubElement(summary, tag("Counters"), counters)
    for offset, method in enumerate(methods, start):
        test_id = "synthetic-test-" + str(offset)
        execution_id = "synthetic-execution-" + str(offset)
        name = TEST_CLASS + "." + method + "(synthetic-" + str(offset) + ")"
        definition = ET.SubElement(definitions, tag("UnitTest"),
                                   id=test_id, name=name)
        ET.SubElement(definition, tag("Execution"), id=execution_id)
        ET.SubElement(definition, tag("TestMethod"),
                      name=method, className=TEST_CLASS + ", SyntheticAssembly")
        ET.SubElement(entries, tag("TestEntry"), testId=test_id,
                      executionId=execution_id)
        ET.SubElement(results, tag("UnitTestResult"), testId=test_id,
                      executionId=execution_id, testName=name, outcome="Passed")
    return root


class SelfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="po-header-trx-self-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, document: ET.Element, filename: str = "focused.trx") -> None:
        ET.ElementTree(document).write(self.root / filename, encoding="utf-8",
                                       xml_declaration=True)

    def expect_rejection(self, code: str) -> None:
        with self.assertRaisesRegex(VerificationError, "^" + code + "$"):
            verify(self.root)

    def test_single_file_passes_exact_135(self) -> None:
        self.write(_synthetic_document(_synthetic_cases()))
        self.assertEqual(verify(self.root)["passed"], 135)

    def test_two_disjoint_files_pass(self) -> None:
        methods = _synthetic_cases()
        self.write(_synthetic_document(methods[:67]), "first.trx")
        self.write(_synthetic_document(methods[67:], 67), "second.trx")
        self.assertEqual(verify(self.root)["trx_files"], 2)

    def test_missing_trx_rejected(self) -> None:
        self.expect_rejection("trx_file_count")

    def test_duplicate_test_id_across_files_rejected(self) -> None:
        methods = _synthetic_cases()
        self.write(_synthetic_document(methods[:67]), "first.trx")
        self.write(_synthetic_document(methods[67:], 0), "second.trx")
        self.expect_rejection("duplicate_test_id")

    def test_duplicate_execution_id_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        entries = document.find("./{*}TestEntries")
        self.assertIsNotNone(entries)
        entries[1].set("executionId", entries[0].get("executionId") or "")
        self.write(document)
        self.expect_rejection("duplicate_execution_id")

    def test_missing_definition_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        definitions = document.find("./{*}TestDefinitions")
        self.assertIsNotNone(definitions)
        definitions.remove(definitions[0])
        self.write(document)
        self.expect_rejection("trx_collection_counts")

    def test_missing_entry_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        entries = document.find("./{*}TestEntries")
        self.assertIsNotNone(entries)
        entries.remove(entries[0])
        self.write(document)
        self.expect_rejection("trx_collection_counts")

    def test_wrong_class_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        method = document.find(".//{*}TestMethod")
        self.assertIsNotNone(method)
        method.set("className", "Synthetic.Foreign")
        self.write(document)
        self.expect_rejection("foreign_test_class")

    def test_wrong_method_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        method = document.find(".//{*}TestMethod")
        self.assertIsNotNone(method)
        method.set("name", "ForeignMethod")
        self.write(document)
        self.expect_rejection("foreign_test_method")

    def test_missing_method_case_rejected(self) -> None:
        self.write(_synthetic_document(_synthetic_cases()[:-1]))
        self.expect_rejection("total_case_count")

    def test_nonpassing_result_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        result = document.find(".//{*}UnitTestResult")
        self.assertIsNotNone(result)
        result.set("outcome", "Failed")
        self.write(document)
        self.expect_rejection("result_outcome")

    def test_nonpassing_counter_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        counters = document.find(".//{*}Counters")
        self.assertIsNotNone(counters)
        counters.set("failed", "1")
        self.write(document)
        self.expect_rejection("counter_value")

    def test_invalid_summary_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        summary = document.find("./{*}ResultSummary")
        self.assertIsNotNone(summary)
        summary.set("outcome", "Failed")
        self.write(document)
        self.expect_rejection("summary_outcome")

    def test_nested_failed_summary_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        wrapper = ET.SubElement(document, "Wrapper")
        summary = ET.SubElement(wrapper, "ResultSummary", outcome="Failed")
        ET.SubElement(summary, "Counters", failed="1")
        self.write(document)
        self.expect_rejection("summary_collection")

    def test_nested_extra_counters_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        wrapper = ET.SubElement(document, "Wrapper")
        ET.SubElement(wrapper, "Counters", failed="1")
        self.write(document)
        self.expect_rejection("counters_collection")

    def test_execution_mismatch_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        definition = document.find(".//{*}Execution")
        self.assertIsNotNone(definition)
        definition.set("id", "different-execution")
        self.write(document)
        self.expect_rejection("execution_join")

    def test_extra_foreign_case_rejected(self) -> None:
        methods = _synthetic_cases() + ["ForeignMethod"]
        self.write(_synthetic_document(methods))
        self.expect_rejection("foreign_test_method")

    def test_foreign_result_row_rejected(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        results = document.find("./{*}Results")
        self.assertIsNotNone(results)
        ET.SubElement(results, "ForeignResult")
        self.write(document)
        self.expect_rejection("foreign_collection_row")

    def test_unsafe_xml_rejected(self) -> None:
        (self.root / "focused.trx").write_bytes(
            b'<!DOCTYPE TestRun [<!ENTITY leak "synthetic">]><TestRun/>')
        self.expect_rejection("trx_unsupported_xml")

    def test_utf8_bom_is_accepted(self) -> None:
        document = _synthetic_document(_synthetic_cases())
        source = ET.tostring(document, encoding="utf-8", xml_declaration=True)
        (self.root / "focused.trx").write_bytes(b"\xef\xbb\xbf" + source)
        self.assertEqual(verify(self.root)["passed"], EXPECTED_CASES)

    def test_utf16_dtd_is_rejected_before_xml_parse(self) -> None:
        source = ('<?xml version="1.0" encoding="UTF-16"?>'
                  '<!DOCTYPE TestRun [<!ENTITY leak "synthetic">]><TestRun/>')
        (self.root / "focused.trx").write_bytes(source.encode("utf-16"))
        self.expect_rejection("trx_unsupported_encoding")

    def test_declared_non_utf8_encoding_is_rejected(self) -> None:
        (self.root / "focused.trx").write_bytes(
            b'<?xml version="1.0" encoding="UTF-16"?><TestRun/>')
        self.expect_rejection("trx_unsupported_encoding")

    def test_actual_read_above_cap_is_rejected(self) -> None:
        with (self.root / "focused.trx").open("wb") as stream:
            stream.seek(MAX_TRX_BYTES)
            stream.write(b"x")
        self.expect_rejection("trx_size_limit")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify focused purchase-order-header TRX")
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        if args.directory is not None:
            parser.error("--self-test does not accept a directory")
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SelfTests)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.directory is None:
        parser.error("a TRX directory is required")
    try:
        summary = verify(Path(args.directory))
    except (VerificationError, OSError, ET.ParseError) as error:
        code = str(error) if isinstance(error, VerificationError) else "trx_io_or_parse"
        print("purchase_order_header_results_rejected:" + code, file=sys.stderr)
        return 1
    print("purchase_order_header_results_verified "
          f"files={summary['trx_files']} methods={summary['methods']} "
          f"passed={summary['passed']} failed={summary['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
