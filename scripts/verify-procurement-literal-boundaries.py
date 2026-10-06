"""Retain actual native source-literal boundary results; full-service coverage is separate."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

EXPECTED = {
    "ProcurementAddressAndFileCreateLiteralSourceTests.PurchaseOrderAddressJsonPostAndPutCopyValidLiteralsAndZeroCountryExactly": 3,
    "ProcurementAddressAndFileCreateLiteralSourceTests.FilePostKeepsPaddedNonEmptyBucketAndDefaultBindingRejectsAllSpace": 2,
    "ProcurementAddressAndFileCreateLiteralSourceTests.MissingWritePermissionCannotPersistEitherLiteralRoute": 2,
}
NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}

def xml(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Require regular artifact")
    raw = path.read_bytes()
    if not raw or len(raw) > 64 * 1024 * 1024:
        raise ValueError("Missing or oversized artifact")
    source = raw.decode("utf-8-sig")
    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        raise ValueError("DTD/entity declarations are forbidden")
    return ET.fromstring(source), hashlib.sha256(raw).hexdigest()

def verify_trx(document):
    if document.tag != "{" + NS["t"] + "}TestRun":
        raise ValueError("Require native TestRun root")
    for name, direct in (("Results", "./t:Results"), ("TestDefinitions", "./t:TestDefinitions"),
                         ("ResultSummary", "./t:ResultSummary"), ("Counters", "./t:ResultSummary/t:Counters")):
        all_nodes = [node for node in document.iter() if node.tag.split("}")[-1] == name]
        if len(all_nodes) != 1 or len(document.findall(direct, NS)) != 1:
            raise ValueError("Duplicate or misplaced native container")
    results = document.findall("./t:Results/t:UnitTestResult", NS)
    definitions = document.findall("./t:TestDefinitions/t:UnitTest", NS)
    if len(results) != len(document.findall(".//t:UnitTestResult", NS)) or len(definitions) != len(document.findall(".//t:UnitTest", NS)):
        raise ValueError("Misplaced native result/definition")
    by_id = {}
    for definition in definitions:
        test_id = str(uuid.UUID(definition.attrib["id"]))
        if test_id in by_id:
            raise ValueError("Duplicate definition")
        method = definition.find("t:TestMethod", NS)
        if method is None:
            raise ValueError("Missing method binding")
        execution = definition.find("t:Execution", NS)
        if execution is None:
            raise ValueError("Missing definition execution")
        by_id[test_id] = (method.attrib["className"].split(",")[0] + "." + method.attrib["name"],
                          str(uuid.UUID(execution.attrib["id"])), definition.attrib["name"])
    methods = collections.Counter()
    executions = set()
    referenced = set()
    display_names = set()
    for result in results:
        execution = str(uuid.UUID(result.attrib["executionId"]))
        if execution in executions or result.get("outcome") != "Passed":
            raise ValueError("Duplicate execution or non-passing case")
        executions.add(execution)
        test_id = str(uuid.UUID(result.attrib["testId"]))
        if test_id in referenced or result.get("testName") in display_names:
            raise ValueError("Repeated native case")
        binding = by_id.get(test_id)
        if binding is None or binding[1] != execution or binding[2] != result.get("testName"):
            raise ValueError("Definition execution/name mismatch")
        method = binding[0]
        matches = [name for name in EXPECTED if method.endswith("." + name)]
        if len(matches) != 1 or matches[0] not in result.get("testName", ""):
            raise ValueError("Unknown or mismatched native case")
        referenced.add(test_id)
        display_names.add(result.get("testName"))
        methods[matches[0]] += 1
    if methods != EXPECTED or referenced != set(by_id):
        raise ValueError("Missing, additional, or incorrect native cases")
    summaries = document.findall("./t:ResultSummary", NS)
    all_counters = document.findall("./t:ResultSummary/t:Counters", NS)
    if len(summaries) != 1 or len(all_counters) != 1:
        raise ValueError("Require exactly one summary/counters")
    summary, counters = summaries[0], all_counters[0]
    if summary.get("outcome") != "Completed":
        raise ValueError("Missing completed summary")
    if set(counters.attrib) != {"total", "executed", "passed", "failed", "error", "timeout", "aborted", "inconclusive", "passedButRunAborted", "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending"}:
        raise ValueError("Missing or unexpected counters")
    for name, value in counters.attrib.items():
        expected = 7 if name in {"total", "executed", "passed"} else 0
        if int(value) != expected:
            raise ValueError("Failed, skipped, incomplete, or incorrect counters")
    return dict(methods)

def bind_source(path, committed):
    if path.is_symlink() or not path.is_file() or path.read_bytes() != committed:
        raise ValueError("Source bytes differ from the tested commit")
    return hashlib.sha256(committed).hexdigest()

def main():
    root = Path(sys.argv[1])
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Require one native TRX")
    document, trx_hash = xml(reports[0])
    methods = verify_trx(document)
    coverage = list(root.rglob("coverage.cobertura.xml"))
    if not coverage:
        raise ValueError("Missing raw coverage")
    parsed = [xml(path) for path in coverage]
    hashes = {digest for _, digest in parsed}
    if len(hashes) != 1:
        raise ValueError("Divergent raw coverage")
    for assembly in ("Api", "Application", "Data", "Domain"):
        selected = [package for package in parsed[0][0].findall("./packages/package")
                    if package.get("name") == "Legacy.Maliev.ProcurementService." + assembly]
        if not selected or not any(package.findall(".//line") for package in selected):
            raise ValueError("Missing executable owned assembly")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], timeout=30).decode("ascii").strip()
    if head != os.environ.get("GITHUB_SHA"):
        raise ValueError("Actual checkout differs from hosted tested commit")
    paths = subprocess.check_output(["git", "ls-files"], timeout=30).decode("utf-8").splitlines()
    sources = [path for path in paths if path.endswith((".cs", ".csproj", ".props", ".targets", ".slnx")) or path in
               {"global.json", "NuGet.Config", "nuget.config", ".editorconfig",
                "scripts/verify-procurement-literal-boundaries.py", ".github/workflows/procurement-literal-boundaries.yml",
                "docs/procurement-focused-lifecycle-contract.json"}]
    bindings = {}
    for path in sources:
        committed = subprocess.check_output(["git", "show", head + ":" + path], timeout=30)
        bindings[path] = bind_source(Path(path), committed)
    proof = {"testedCommit": head, "runId": os.environ["GITHUB_RUN_ID"], "runAttempt": os.environ["GITHUB_RUN_ATTEMPT"],
             "passed": 7, "failed": 0, "skipped": 0, "methods": methods, "trxSha256": trx_hash,
             "rawSha256": next(iter(hashes)), "exclusions": [], "sourceBindings": bindings,
             "fullServiceCoverageAcceptance": False, "actualAuthProducerAcceptance": False,
             "originalSqlServerExecuted": False, "persistentSchemaApplied": False}
    destination = root / "source-literal-proof.json"
    if destination.exists():
        raise ValueError("Refuse to rewrite an existing native receipt")
    destination.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2))

if __name__ == "__main__":
    main()
