"""Require actual standalone executions of the frozen 19 authored startup Facts."""
import hashlib
import json
import pathlib
import sys
import uuid
import xml.etree.ElementTree as ET


def guid(value):
    if str(uuid.UUID(value or "")) != value:
        raise ValueError("Noncanonical execution or test GUID.")
    return value


def verify(root, manifest):
    if set(manifest) != {"expectedCases", "className", "methods", "guidStatus"}:
        raise ValueError("Unexpected roster fields.")
    methods = manifest["methods"]
    if manifest["expectedCases"] != 19 or len(methods) != 19 or len(set(methods)) != 19:
        raise ValueError("Exactly 19 distinct authored methods are required.")
    if manifest["className"] != "Legacy.Maliev.ProcurementService.Tests.Integration.ProcurementFixtureStartupJournalTests":
        raise ValueError("Foreign test class.")
    if manifest["guidStatus"] != "Native GUIDs NOT RUN; preserve first actual joins without inventing IDs":
        raise ValueError("Unknown GUID provenance.")
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Exactly one standalone TRX is required.")
    document = ET.parse(reports[0]).getroot()
    if document.tag.rsplit("}", 1)[-1] != "TestRun" or document.findall(".//{*}TestRun"):
        raise ValueError("One actual TestRun root is required.")
    for tag in ("ResultSummary", "TestDefinitions", "TestEntries", "Results"):
        direct = document.findall("./{*}" + tag)
        if len(direct) != 1 or document.findall(".//{*}" + tag) != direct:
            raise ValueError("Nested or duplicate result containers are forbidden.")
    summaries = document.findall("./{*}ResultSummary")
    if len(summaries) != 1 or summaries[0].get("outcome") != "Completed":
        raise ValueError("One completed root summary is required.")
    counters = summaries[0].findall("./{*}Counters")
    if document.findall(".//{*}Counters") != counters:
        raise ValueError("Nested or duplicate counters are forbidden.")
    zeros = ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted", "notRunnable",
             "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")
    expected = {key: "0" for key in zeros}
    expected.update(total="19", executed="19", passed="19")
    if len(counters) != 1 or counters[0].attrib != expected:
        raise ValueError("All 19 cases must execute and pass with every other counter zero.")
    if document.findall(".//{*}ErrorInfo") or document.findall(".//{*}RunInfo"):
        raise ValueError("Run or error information is forbidden.")
    definitions = document.findall("./{*}TestDefinitions/{*}UnitTest")
    entries = document.findall("./{*}TestEntries/{*}TestEntry")
    results = document.findall("./{*}Results/{*}UnitTestResult")
    for tag, direct in (("UnitTest", definitions), ("TestEntry", entries), ("UnitTestResult", results)):
        if document.findall(".//{*}" + tag) != direct:
            raise ValueError("Nested or foreign structural execution rows are forbidden.")
    if any(len(values) != 19 for values in (definitions, entries, results)):
        raise ValueError("Definition/result/entry cardinality differs.")
    defs = {guid(value.get("id")): value for value in definitions}
    joins = {guid(value.get("testId")): guid(value.get("executionId")) for value in entries}
    if len(defs) != 19 or len(joins) != 19:
        raise ValueError("Duplicate identities.")
    names, executions, ids = set(), set(), set()
    identities = []
    all_methods, all_executions = [], []
    for definition in definitions:
        method = definition.findall("./{*}TestMethod")
        execution = definition.findall("./{*}Execution")
        if (len(method) != 1 or len(execution) != 1 or definition.findall(".//{*}TestMethod") != method
                or definition.findall(".//{*}Execution") != execution):
            raise ValueError("Each definition requires singleton direct method and execution metadata.")
        all_methods.extend(method)
        all_executions.extend(execution)
    if document.findall(".//{*}TestMethod") != all_methods or document.findall(".//{*}Execution") != all_executions:
        raise ValueError("Foreign method or execution metadata is forbidden.")
    for result in results:
        test_id, execution = guid(result.get("testId")), guid(result.get("executionId"))
        name = result.get("testName")
        definition = defs.get(test_id)
        if definition is None or name in names or test_id in ids or execution in executions:
            raise ValueError("Duplicate or unbound execution.")
        method = definition.findall("./{*}TestMethod")
        defined_execution = definition.findall("./{*}Execution")
        if (len(method) != 1 or len(defined_execution) != 1 or result.get("outcome") != "Passed"
                or definition.get("name") != name or defined_execution[0].get("id") != execution
                or joins.get(test_id) != execution or method[0].get("className") != manifest["className"]
                or method[0].get("name") not in methods
                or name != manifest["className"] + "." + method[0].get("name")
                or not method[0].get("codeBase", "").replace("\\", "/").endswith("/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll")):
            raise ValueError("Actual method/assembly/definition/result/entry join differs.")
        names.add(name)
        ids.add(test_id)
        executions.add(execution)
        identities.append({"name": name, "testId": test_id, "executionId": execution})
    if names != {manifest["className"] + "." + method for method in methods}:
        raise ValueError("Authored roster differs.")
    proof = {"passed": 19, "failed": 0, "skipped": 0, "identities": sorted(identities, key=lambda value: value["name"]),
             "trxSha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
             "nativeGuidProvenance": "First actual standalone TRX joins; no prior native GUID forecast",
             "fullSuiteAcceptance": False, "productionQualification": False}
    (root / "startup-journal-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    manifest = json.loads(pathlib.Path("docs/procurement-startup-journal-contract.json").read_text(encoding="utf-8"))
    print(json.dumps(verify(pathlib.Path(sys.argv[1]), manifest)))
