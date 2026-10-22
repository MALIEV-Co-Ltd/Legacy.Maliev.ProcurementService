"""Require the separately executed, frozen 28 workflow regressions and raw evidence."""
import hashlib
import json
import pathlib
import sys
import uuid
import xml.etree.ElementTree as ET


def verify(root, manifest):
    expected = {(v["name"], v["id"]) for v in manifest["cases"]}
    if manifest["expectedCases"] != 28 or len(expected) != 28 or len(manifest["cases"]) != 28:
        raise ValueError("The reviewed focused roster must contain exactly 28 distinct identities.")
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Exactly one separate focused TRX is required.")
    document = ET.parse(reports[0])
    run = document.getroot()
    namespace = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
    if run.tag != namespace + "TestRun" or any(
            not isinstance(node.tag, str) or not node.tag.startswith(namespace) for node in run.iter()):
        raise ValueError("Only the TeamTest 2010 TestRun namespace is accepted.")

    def direct_singleton(parent, name):
        direct = parent.findall("./" + namespace + name)
        global_nodes = list(run.iter(namespace + name))
        if len(direct) != 1 or len(global_nodes) != 1 or global_nodes[0] is not direct[0]:
            raise ValueError("TRX containers and summary counters must be unique and direct.")
        return direct[0]

    definition_container = direct_singleton(run, "TestDefinitions")
    entry_container = direct_singleton(run, "TestEntries")
    result_container = direct_singleton(run, "Results")
    summary = direct_singleton(run, "ResultSummary")
    counters = direct_singleton(summary, "Counters")
    if summary.get("outcome") != "Completed":
        raise ValueError("The focused run must complete without an adverse summary outcome.")
    if list(run.iter(namespace + "RunInfo")) or list(run.iter(namespace + "ErrorInfo")):
        raise ValueError("Focused run notices and error evidence are forbidden.")
    definitions = definition_container.findall("./" + namespace + "UnitTest")
    entries = entry_container.findall("./" + namespace + "TestEntry")
    results = result_container.findall("./" + namespace + "UnitTestResult")
    for name, rows in (("UnitTest", definitions), ("TestEntry", entries), ("UnitTestResult", results)):
        if len(rows) != 28 or len(list(run.iter(namespace + name))) != 28:
            raise ValueError("Focused cardinality or direct/global result custody differs.")
    nonpassing = ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
                  "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")
    required_counters = {"total": "28", "executed": "28", "passed": "28",
                         **{name: "0" for name in nonpassing}}
    if counters.attrib != required_counters:
        raise ValueError("All 16 focused counters must report exactly 28 passed and no adverse outcome.")
    if len(list(run.iter(namespace + "Execution"))) != 28:
        raise ValueError("Every focused definition must own exactly one execution.")
    defs = {v.get("id"): v for v in definitions}
    joins = {v.get("testId"): v.get("executionId") for v in entries}
    if len(defs) != 28 or len(joins) != 28:
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
        defined_executions = definition.findall("./" + namespace + "Execution")
        defined_execution = defined_executions[0] if len(defined_executions) == 1 else None
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
    proof = {"passed": 28, "failed": 0, "skipped": 0, "strictTrxJoins": True,
             "identities": sorted(actual), "trxSha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
             "rawCoverageSha256": next(iter(digests)), "rawCopies": len(coverage), "exclusions": [],
             "fullServiceCoverageAcceptance": False, "productionEnrollmentProven": False}
    (root / "focused-workflow-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    manifest = json.loads(pathlib.Path("docs/procurement-focused-workflow-contract.json").read_text(encoding="utf-8"))
    print(json.dumps(verify(pathlib.Path(sys.argv[1]), manifest)))
