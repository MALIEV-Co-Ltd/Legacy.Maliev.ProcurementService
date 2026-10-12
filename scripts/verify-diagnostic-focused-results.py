"""Require actual standalone executions of the frozen authored diagnostic and inherited durable cases."""
import hashlib
import json
import pathlib
import sys
import uuid
import xml.etree.ElementTree as ET


CONTRACT_SHA256 = 'f26a279bc845760253b6a483b459a608443c2113775dea54877529a77ac46603'

def guid(value):
    if str(uuid.UUID(value or "")) != value:
        raise ValueError("Noncanonical execution or test GUID.")
    return value


def verify(root, manifest, cohort):
    if hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() != CONTRACT_SHA256:
        raise ValueError("Frozen diagnostic/durable source contract differs.")
    selected = [row for row in manifest["cases"] if row["cohort"] == cohort]
    if cohort not in manifest["cohortCounts"]:
        raise ValueError("Unknown focused cohort.")
    count = manifest["cohortCounts"][cohort]
    expected_rows = {row["name"]: row for row in selected}
    if len(selected) != count or len(expected_rows) != count:
        raise ValueError("Exact distinct focused cohort required.")
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
    expected.update(total=str(count), executed=str(count), passed=str(count))
    if len(counters) != 1 or counters[0].attrib != expected:
        raise ValueError("All focused cases must execute and pass with every other counter zero.")
    if document.findall(".//{*}ErrorInfo") or document.findall(".//{*}RunInfo"):
        raise ValueError("Run or error information is forbidden.")
    definitions = document.findall("./{*}TestDefinitions/{*}UnitTest")
    entries = document.findall("./{*}TestEntries/{*}TestEntry")
    results = document.findall("./{*}Results/{*}UnitTestResult")
    for tag, direct in (("UnitTest", definitions), ("TestEntry", entries), ("UnitTestResult", results)):
        if document.findall(".//{*}" + tag) != direct:
            raise ValueError("Nested or foreign structural execution rows are forbidden.")
    if any(len(values) != count for values in (definitions, entries, results)):
        raise ValueError("Definition/result/entry cardinality differs.")
    defs = {guid(value.get("id")): value for value in definitions}
    joins = {guid(value.get("testId")): guid(value.get("executionId")) for value in entries}
    if len(defs) != count or len(joins) != count:
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
                or joins.get(test_id) != execution or name not in expected_rows or method[0].get("className") != expected_rows[name]["className"]
                or method[0].get("name") != expected_rows[name]["method"]
                or name != expected_rows[name]["name"]
                or not method[0].get("codeBase", "").replace("\\", "/").endswith("/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll")):
            raise ValueError("Actual method/assembly/definition/result/entry join differs.")
        names.add(name)
        ids.add(test_id)
        executions.add(execution)
        identities.append({"name": name, "testId": test_id, "executionId": execution})
    if names != set(expected_rows):
        raise ValueError("Authored roster differs.")
    proof = {"passed": count, "failed": 0, "skipped": 0, "identities": sorted(identities, key=lambda value: value["name"]),
             "trxSha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
             "nativeGuidProvenance": "First actual standalone TRX joins; no prior native GUID forecast",
             "fullSuiteAcceptance": False, "productionQualification": False}
    (root / "diagnostic-focused-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


def load_contract():
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate contract key.")
            result[key] = value
        return result
    manifest = json.loads(pathlib.Path("docs/procurement-diagnostic-focused-contract.json").read_text(encoding="utf-8"), object_pairs_hook=unique)
    if hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() != CONTRACT_SHA256:
        raise ValueError("Frozen contract drift.")
    for path, expected in manifest["sourceHashes"].items():
        if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("Focused C# source enrollment drift.")
    return manifest


if __name__ == "__main__":
    manifest = load_contract()
    if sys.argv[1:] == ["--source-contract"]:
        print(json.dumps({"sourceContract": "PASS", "nativeExecuted": False}))
    elif len(sys.argv) == 3:
        print(json.dumps(verify(pathlib.Path(sys.argv[1]), manifest, sys.argv[2])))
    else:
        raise ValueError("Require source-contract or result root and exact cohort.")
