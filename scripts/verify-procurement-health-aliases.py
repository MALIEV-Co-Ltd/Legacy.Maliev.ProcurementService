"""Require five real health-alias executions; this is not full-service or provider acceptance."""
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import xml.etree.ElementTree as ET

REPOSITORY = Path(__file__).resolve().parent.parent
CLASS = "Legacy.Maliev.ProcurementService.Tests.Controllers.LegacyProcurementHealthHttpTests"
METHODS = (
    "LegacyLiveness_PreservesAnonymousVerbsAndCaseWithoutDependencyCalls",
    "Readiness_PreservesPrivateFailureDeduplicationAndSuccessReset",
    "LegacyReadiness_IncludesUntaggedChecksUnderCurrentStrongerPolicy",
    "LegacyAliases_DoNotAcquireCurrentHealthInstanceHeaders",
    "HealthAliases_PreserveBusinessAuthenticationAndNearRouteMisses",
)
SOURCE_HASHES = {
    "Legacy.Maliev.ProcurementService.Api/Program.cs": "a19bf446003715e73ab5161eda4c884e80a06ad2c12d0d23a5be6d670286720e",
    "Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs": "730e0cfde2314b27403f3ed15e653d4436b06e268070b134e93e198ca9ba3d34",
    "Legacy.Maliev.ProcurementService.Api/Controllers/LegacyProcurementHealthController.cs": "559531d9d7badf5dd2111dfeb2a9872c45eefd3256d2a89c869a9135c16229f9",
    "Legacy.Maliev.ProcurementService.Tests/Controllers/LegacyProcurementHealthHttpTests.cs": "4e62e3218928bffa759130527149bcd48da1c30fee6ba52951bb50f530688152"
}
SOURCE_PATHS = {
    "Legacy.Maliev.ProcurementService.Api/Program.cs",
    "Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs",
    "Legacy.Maliev.ProcurementService.Api/Controllers/LegacyProcurementHealthController.cs",
    "Legacy.Maliev.ProcurementService.Tests/Controllers/LegacyProcurementHealthHttpTests.cs",
}
NAMESPACE = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"


def verify_sources(source_root):
    if set(SOURCE_HASHES) != SOURCE_PATHS:
        raise ValueError("Require all four reviewed production, IAM and test source bindings.")
    for path, expected in SOURCE_HASHES.items():
        if hashlib.sha256((source_root / path).read_bytes()).hexdigest() != expected:
            raise ValueError("Reviewed health alias source changed: " + path)


def bounded_xml(path, maximum):
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Evidence exceeds its finite byte bound.")
    text = data.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("DTD and entity declarations are forbidden.")
    return ET.fromstring(text), hashlib.sha256(data).hexdigest()


def canonical_guid(value):
    try:
        parsed = uuid.UUID(value or "")
    except (ValueError, AttributeError) as error:
        raise ValueError("A canonical nonzero native GUID is required.") from error
    if not parsed.int or str(parsed) != value:
        raise ValueError("A canonical nonzero native GUID is required.")
    return value


def verify(root, source_root=REPOSITORY):
    verify_sources(source_root)
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Require exactly one separate health-alias TRX.")
    run, trx_hash = bounded_xml(reports[0], 32 * 1024 * 1024)
    if run.tag != NAMESPACE + "TestRun" or any(
            not isinstance(node.tag, str) or not node.tag.startswith(NAMESPACE) for node in run.iter()):
        raise ValueError("Require the exact TeamTest 2010 namespace.")

    def singleton(parent, name):
        direct = parent.findall("./" + NAMESPACE + name)
        global_nodes = list(run.iter(NAMESPACE + name))
        if len(direct) != 1 or len(global_nodes) != 1 or global_nodes[0] is not direct[0]:
            raise ValueError("Evidence containers must be unique and direct.")
        return direct[0]

    definitions_node = singleton(run, "TestDefinitions")
    entries_node = singleton(run, "TestEntries")
    results_node = singleton(run, "Results")
    summary = singleton(run, "ResultSummary")
    counters = singleton(summary, "Counters")
    if summary.get("outcome") != "Completed" or list(run.iter(NAMESPACE + "RunInfo")) or list(run.iter(NAMESPACE + "ErrorInfo")):
        raise ValueError("Require completed evidence without adverse notices or errors.")
    groups = ((definitions_node, "UnitTest"), (entries_node, "TestEntry"), (results_node, "UnitTestResult"))
    for container, name in groups:
        if len(container) != 5 or len(container.findall(NAMESPACE + name)) != 5 or len(list(run.iter(NAMESPACE + name))) != 5:
            raise ValueError("Require exactly five direct definitions, entries and results.")
    if len(list(run.iter(NAMESPACE + "Execution"))) != 5 or len(list(run.iter(NAMESPACE + "TestMethod"))) != 5:
        raise ValueError("Require one execution and method per definition.")
    adverse = ("failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted", "notRunnable",
               "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")
    expected_counters = {"total": "5", "executed": "5", "passed": "5", **{name: "0" for name in adverse}}
    if counters.attrib != expected_counters:
        raise ValueError("All sixteen counters must require five passed and no adverse outcomes.")
    expected = {CLASS + "." + method for method in METHODS}
    definitions = {}
    defined_executions = set()
    for definition in definitions_node:
        test_id = canonical_guid(definition.get("id"))
        executions = definition.findall(NAMESPACE + "Execution")
        methods = definition.findall(NAMESPACE + "TestMethod")
        if test_id in definitions or len(executions) != 1 or len(methods) != 1:
            raise ValueError("Duplicate or incomplete definition.")
        execution = canonical_guid(executions[0].get("id"))
        identity = methods[0].get("className", "") + "." + methods[0].get("name", "")
        if identity not in expected or definition.get("name") != identity or execution in defined_executions:
            raise ValueError("Unreviewed identity or duplicate definition execution.")
        definitions[test_id] = (identity, execution)
        defined_executions.add(execution)
    entries = {}
    for entry in entries_node:
        test_id = canonical_guid(entry.get("testId"))
        execution = canonical_guid(entry.get("executionId"))
        if test_id in entries or test_id not in definitions or definitions[test_id][1] != execution:
            raise ValueError("Entry does not join its exact definition.")
        entries[test_id] = execution
    actual, used, executions = set(), set(), set()
    for result in results_node:
        test_id = canonical_guid(result.get("testId"))
        execution = canonical_guid(result.get("executionId"))
        identity = result.get("testName")
        if (result.get("outcome") != "Passed" or test_id in used or execution in executions or identity in actual
                or definitions.get(test_id) != (identity, execution) or entries.get(test_id) != execution):
            raise ValueError("Result does not join one passing reviewed execution.")
        actual.add(identity)
        used.add(test_id)
        executions.add(execution)
    if actual != expected or used != set(definitions) or used != set(entries):
        raise ValueError("The exact five named health regressions must all execute.")
    coverage = list(root.rglob("coverage.cobertura.xml"))
    hashes = set()
    for path in coverage:
        document, digest = bounded_xml(path, 64 * 1024 * 1024)
        if document.tag != "coverage" or not document.findall("./packages/package/classes/class/lines/line"):
            raise ValueError("Require nonempty raw coverage without synthetic acceptance claims.")
        hashes.add(digest)
    if len(hashes) != 1:
        raise ValueError("Require raw coverage with identical copies.")
    proof = {"passed": 5, "failed": 0, "skipped": 0, "identities": sorted(actual), "strictTrxJoins": True,
             "sourceSha256": SOURCE_HASHES, "trxSha256": trx_hash, "rawCoverageSha256": next(iter(hashes)),
             "rawCopies": len(coverage), "exclusions": [], "fullServiceAcceptance": False,
             "providerOrFinancialExecutionAcceptance": False}
    (root / "procurement-health-alias-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
