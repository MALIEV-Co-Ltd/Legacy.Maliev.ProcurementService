"""Strict actual supplier ignored-identity evidence; synthetic controls are separate."""
import datetime
import hashlib
import json
import pathlib
import re
import sys
import uuid
import xml.etree.ElementTree as ET

NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
MAX_TRX_BYTES = 16 * 1024 * 1024
MAX_COVERAGE_BYTES = 16 * 1024 * 1024
MAX_COVERAGE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_COVERAGE_FILES = 4
MAX_JSON_BYTES = 2 * 1024 * 1024
ADVERSE = ("error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
           "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")


def require(value, message):
    if not value:
        raise ValueError(message)


def read_bounded(path, maximum):
    require(maximum >= 0, "Negative evidence budget")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Evidence is empty or exceeds its actual byte bound")
    return raw


def read_json(path):
    return json.loads(read_bounded(path, MAX_JSON_BYTES).decode("utf-8-sig", errors="strict"))


def parse_xml(raw):
    text = raw.decode("utf-8-sig", errors="strict")
    require("\0" not in text and not re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE),
            "NUL/DTD/entity declarations forbidden")
    return ET.fromstring(text)


def reports(directory, pattern, maximum):
    found = []
    for path in directory.rglob(pattern):
        require(len(found) < maximum, "Too many phase evidence files")
        found.append(path)
    return found


def one(parent, name):
    found = parent.findall("./" + NS + name)
    require(len(found) == 1, "Missing/duplicate direct TRX element: " + name)
    return found[0]


def canonical(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def verify_failure(error, case, profile):
    message = one(error, "Message").text or ""
    stack = one(error, "StackTrace").text or ""
    failure = case["failure"]
    if failure["kind"] == "status":
        require("Assert.Equal() Failure: Values differ" in message
                and re.search(r"^Expected:\s*" + re.escape(failure["expected"]) + r"\s*$", message, re.MULTILINE)
                and re.search(r"^Actual:\s*" + re.escape(failure["actual"]) + r"\s*$", message, re.MULTILINE),
                "Baseline is not the exact status assertion caused by ignored input")
    else:
        require(failure["kind"] == "converter" and "Assert.Equal() Failure: Strings differ" in message
                and failure["expected"] in message,
                "Baseline converter admission assertion missing")
    frame = (r"^[ \t]*at " + re.escape(case["class"] + "." + case["method"])
             + r"\([^\r\n]*\) in [^\r\n]*[/\\]" + re.escape(pathlib.Path(profile["testPath"]).name)
             + r":line " + str(case["sourceLine"]) + r"\r?$")
    require(re.search(frame, stack, re.MULTILINE), "Baseline is detached from its frozen assertion site")


# Candidate shape is pinned to the actual retained107-definition witness.
# Baseline inserts only the reviewed workflow's immutable checkout directory.
ASSEMBLY_WORKSPACE = "/home/runner/work/Legacy.Maliev.ProcurementService/Legacy.Maliev.ProcurementService"
ASSEMBLY_SUFFIX = "Legacy.Maliev.ProcurementService.Tests/bin/Release/net10.0/Legacy.Maliev.ProcurementService.Tests.dll"
ASSEMBLY_ADAPTER = "executor://xunit/VsTestRunner3/netcore/"


def require_assembly(definition, method, manifest, phase):
    bindings = manifest["assemblyBindings"]
    require(set(bindings) == {"baseline", "candidate"}, "Wrong closed assembly phase roster")
    expected_code_base = ASSEMBLY_WORKSPACE + (
        "/.supplier-identity-baseline/" if phase == "baseline" else "/") + ASSEMBLY_SUFFIX
    expected = {"storage": expected_code_base.lower(), "codeBase": expected_code_base,
                "adapterTypeName": ASSEMBLY_ADAPTER}
    require(bindings[phase] == expected, "Reviewed Release assembly binding changed")
    require(definition.get("storage") == expected["storage"]
            and method.get("codeBase") == expected["codeBase"]
            and method.get("adapterTypeName") == expected["adapterTypeName"],
            "Actual definition must bind exact reviewed Release/net10.0 test assembly and adapter")


def verify(directory, manifest, phase, family, exit_code, baseline_directory=None, record_proof=True):
    require(phase in ("baseline", "candidate") and family in ("id", "address"), "Unknown phase/family")
    require(exit_code == (1 if phase == "baseline" else 0), "Wrong actual test process exit")
    profile = manifest["profiles"][family]
    count = 55 if family == "id" else 52
    require(profile["testClass"] == "Legacy.Maliev.ProcurementService.Tests.Integration."
            + ("ProcurementSupplierIgnoredIdTests" if family == "id" else "ProcurementSupplierIgnoredAddressIdTests"),
            "Wrong immutable test class")
    cases = profile["cases"]
    require(profile["expectedCases"] == count and len(cases) == count
            and manifest["expectedTotalCases"] == 107
            and len({case["name"] for case in cases}) == count, "Frozen profile roster cardinality")
    passed = profile["baselinePassed"] if phase == "baseline" else count
    failed = profile["baselineFailed"] if phase == "baseline" else 0
    require((profile["baselinePassed"], profile["baselineFailed"]) == ((26, 29) if family == "id" else (30, 22)),
            "Wrong frozen baseline outcomes")
    expected = {case["name"]: case for case in cases}
    paths = reports(directory, "*.trx", 1)
    require(len(paths) == 1, "One isolated actual TRX required")
    raw = read_bounded(paths[0], MAX_TRX_BYTES)
    root = parse_xml(raw)
    require(root.tag == NS + "TestRun" and all(isinstance(node.tag, str) and node.tag.startswith(NS) for node in root.iter()),
            "Exact TeamTest2010 namespace/root required")
    groups = {name: one(root, name) for name in ("TestDefinitions", "TestEntries", "Results", "ResultSummary")}
    for name in (*groups, "Counters"):
        require(len(list(root.iter(NS + name))) == 1, "Nested/duplicate TRX container")
    summary = groups["ResultSummary"]
    require(summary.get("outcome") == ("Failed" if phase == "baseline" else "Completed"), "Wrong phase summary")
    wanted = {"total": str(count), "executed": str(count), "passed": str(passed), "failed": str(failed),
              **{key: "0" for key in ADVERSE}}
    require(one(summary, "Counters").attrib == wanted, "Every exact phase counter required")
    rows = {}
    for group, child in (("TestDefinitions", "UnitTest"), ("TestEntries", "TestEntry"), ("Results", "UnitTestResult")):
        rows[child] = groups[group].findall("./" + NS + child)
        require(len(rows[child]) == count == len(list(root.iter(NS + child))), "Direct/global row cardinality")
        require(len(groups[group]) == count, "Foreign direct TRX row")
    require(len(list(root.iter(NS + "Execution"))) == count
            and len(list(root.iter(NS + "TestMethod"))) == count, "Extra/missing definition child")
    definitions = {row.get("id"): row for row in rows["UnitTest"]}
    entries = {row.get("testId"): row.get("executionId") for row in rows["TestEntry"]}
    require(len(definitions) == len(entries) == count, "Duplicate definition/entry identity")
    names, execution_ids, identities, failures = set(), set(), {}, set()
    for row in rows["UnitTestResult"]:
        name, identity, execution = row.get("testName"), row.get("testId"), row.get("executionId")
        require(name in expected and name not in names and canonical(identity) and canonical(execution)
                and execution not in execution_ids, "Unknown/duplicate/invalid actual case identity")
        case, definition = expected[name], definitions.get(identity)
        require(definition is not None and definition.get("name") == name
                and one(definition, "Execution").get("id") == entries.get(identity) == execution,
                "Actual definition/entry/result three-way join")
        method = one(definition, "TestMethod")
        require_assembly(definition, method, manifest, phase)
        require(method.get("name") == case["method"] and case["class"] == profile["testClass"]
                and method.get("className") == case["class"], "Wrong frozen method/class")
        outcome = case["baselineOutcome"] if phase == "baseline" else "Passed"
        require(row.get("outcome") == outcome, "Wrong individual case outcome")
        errors = row.findall(".//" + NS + "ErrorInfo")
        if outcome == "Passed":
            require(not errors, "Passing case contains failure evidence")
        else:
            require(len(errors) == 1, "One causal baseline error required")
            verify_failure(errors[0], case, profile)
            failures.add(name)
        names.add(name)
        execution_ids.add(execution)
        identities[name] = identity
    require(names == set(expected) and len(set(identities.values())) == count
            and len(failures) == failed and len(list(root.iter(NS + "ErrorInfo"))) == failed,
            "Incomplete/duplicated identities or extra error evidence")
    notice_groups = summary.findall("./" + NS + "RunInfos")
    require(len(notice_groups) <= 1 and len(list(root.iter(NS + "RunInfos"))) == len(notice_groups),
            "Misplaced/duplicate RunInfos")
    notices = notice_groups[0].findall("./" + NS + "RunInfo") if notice_groups else []
    require(not notice_groups or (not notice_groups[0].attrib and len(notice_groups[0]) == len(notices)),
            "Unexpected RunInfos content")
    require(len(list(root.iter(NS + "RunInfo"))) == len(notices) == failed, "Baseline notices must biject with failures")
    noticed = set()
    for notice in notices:
        require(set(notice.attrib) == {"computerName", "outcome", "timestamp"}
                and notice.get("outcome") == "Error" and bool(notice.get("computerName", "").strip())
                and len(notice) == 1, "Malformed notice metadata")
        stamp = notice.get("timestamp", "")
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,7}(?:Z|[+-]\d{2}:\d{2})", stamp)
                and datetime.datetime.fromisoformat(stamp).tzinfo is not None, "Unzoned notice")
        text = one(notice, "Text")
        require(not text.attrib and not len(text), "Unexpected notice text children")
        match = re.fullmatch(r"\[xUnit\.net \d{2}:\d{2}:\d{2}\.\d{2}\]     (.+) \[FAIL\]", text.text or "")
        require(match is not None and match.group(1) in failures and match.group(1) not in noticed,
                "Unmapped/duplicate baseline notice")
        noticed.add(match.group(1))
    require(noticed == failures, "Missing baseline notice")
    coverage = reports(directory, "coverage.cobertura.xml", MAX_COVERAGE_FILES)
    require(bool(coverage), "Raw focused coverage required")
    remaining, digests, executable = MAX_COVERAGE_TOTAL_BYTES, set(), False
    for index, path in enumerate(coverage):
        snapshot = read_bounded(path, min(MAX_COVERAGE_BYTES, remaining))
        remaining -= len(snapshot)
        digests.add(hashlib.sha256(snapshot).hexdigest())
        if index == 0:
            executable = bool(parse_xml(snapshot).findall("./packages/package/classes/class/lines/line"))
    require(len(digests) == 1 and executable, "Empty/inconsistent raw coverage")
    if phase == "candidate":
        require(baseline_directory is not None, "Candidate needs bound actual baseline")
        retained = read_json(baseline_directory / "supplier-identity-proof.json")
        baseline = verify(baseline_directory, manifest, "baseline", family, 1, record_proof=False)
        require(retained == baseline and identities == baseline["identities"], "Baseline raw proof/actual identity set changed")
    proof = {"phase": phase, "family": family, "passed": passed, "failed": failed, "skipped": 0,
             "identities": identities, "trxSha256": hashlib.sha256(raw).hexdigest(),
             "rawCoverageSha256": next(iter(digests)), "rawCopies": len(coverage),
             "wholeSourceModelParity": False, "fullServiceCoverageAcceptance": False, "productionEnrollmentProven": False}
    if record_proof:
        path = directory / "supplier-identity-proof.json"
        if path.exists():
            require(read_json(path) == proof, "Preserved proof must not be overwritten")
        else:
            path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    directory, phase, family, code = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
    prior = pathlib.Path(sys.argv[5]) if len(sys.argv) == 6 else None
    manifest = read_json(pathlib.Path("docs/procurement-supplier-identity-contract.json"))
    proof = verify(directory, manifest, phase, family, code, prior)
    print(json.dumps({key: proof[key] for key in ("phase", "family", "passed", "failed", "skipped")}))
