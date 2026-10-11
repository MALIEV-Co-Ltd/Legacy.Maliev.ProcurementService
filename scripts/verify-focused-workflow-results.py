"""Require the separately executed, frozen 27 workflow regressions and raw evidence."""
import hashlib
import json
import pathlib
import sys
import uuid
import xml.etree.ElementTree as ET


def verify(root, manifest):
    expected = {(v["name"], v["id"]) for v in manifest["cases"]}
    if manifest["expectedCases"] != 27 or len(expected) != 27 or len(manifest["cases"]) != 27:
        raise ValueError("The reviewed focused roster must contain exactly 27 distinct identities.")
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Exactly one separate focused TRX is required.")
    document = ET.parse(reports[0])
    definitions = document.findall(".//{*}TestDefinitions/{*}UnitTest")
    entries = document.findall(".//{*}TestEntries/{*}TestEntry")
    results = document.findall(".//{*}Results/{*}UnitTestResult")
    counters = document.find(".//{*}Counters")
    if counters is None or any(int(counters.get(k, "-1")) != 27 for k in ("total", "executed", "passed")):
        raise ValueError("All 27 focused cases must execute and pass.")
    nonpassing = ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
                  "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")
    if any(int(counters.get(k, "-1")) != 0 for k in nonpassing):
        raise ValueError("Failed or skipped focused cases are forbidden.")
    if len(definitions) != 27 or len(entries) != 27 or len(results) != 27 or document.findall(".//{*}ErrorInfo"):
        raise ValueError("Focused cardinality or error evidence differs.")
    defs = {v.get("id"): v for v in definitions}
    joins = {v.get("testId"): v.get("executionId") for v in entries}
    if len(defs) != 27 or len(joins) != 27:
        raise ValueError("Duplicate definitions or entries are forbidden.")
    actual, executions = set(), set()
    for result in results:
        key = (result.get("testName"), result.get("testId"))
        execution = result.get("executionId")
        try:
            canonical_execution = str(uuid.UUID(execution or ""))
        except (ValueError, AttributeError) as error:
            raise ValueError("Focused execution IDs must be canonical GUIDs.") from error
        if canonical_execution != execution:
            raise ValueError("Focused execution IDs must be canonical GUIDs.")
        definition = defs.get(key[1])
        if key in actual or not execution or execution in executions or definition is None:
            raise ValueError("Duplicate or unbound focused execution.")
        defined_execution = definition.find("./{*}Execution")
        if (result.get("outcome") != "Passed" or definition.get("name") != key[0]
                or defined_execution is None or defined_execution.get("id") != execution
                or joins.get(key[1]) != execution):
            raise ValueError("Focused definition/result/entry joins or outcomes differ.")
        actual.add(key)
        executions.add(execution)
    if actual != expected:
        raise ValueError("Focused names and IDs differ from the frozen reviewed roster.")
    coverage = list(root.rglob("coverage.cobertura.xml"))
    digests = {hashlib.sha256(v.read_bytes()).hexdigest() for v in coverage}
    if len(digests) != 1 or not ET.parse(coverage[0]).findall("./packages/package/classes/class/lines/line"):
        raise ValueError("Nonempty raw focused coverage with identical copies is required.")
    proof = {"passed": 27, "failed": 0, "skipped": 0, "strictTrxJoins": True,
             "identities": sorted(actual), "trxSha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
             "rawCoverageSha256": next(iter(digests)), "rawCopies": len(coverage), "exclusions": [],
             "fullServiceCoverageAcceptance": False, "productionEnrollmentProven": False}
    (root / "focused-workflow-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    manifest = json.loads(pathlib.Path("docs/procurement-focused-workflow-contract.json").read_text(encoding="utf-8"))
    print(json.dumps(verify(pathlib.Path(sys.argv[1]), manifest)))
