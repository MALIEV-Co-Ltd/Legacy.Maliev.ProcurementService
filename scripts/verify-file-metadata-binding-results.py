"""Accept only the frozen file-metadata roster and actual phase evidence."""
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
MAX_COVERAGE_FILE_BYTES = 16 * 1024 * 1024
MAX_COVERAGE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_COVERAGE_FILES = 4
MAX_JSON_BYTES = 2 * 1024 * 1024
ADVERSE = ("error", "timeout", "aborted", "inconclusive", "passedButRunAborted",
           "notRunnable", "notExecuted", "disconnected", "warning", "completed", "inProgress", "pending")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def one(parent, tag):
    rows = parent.findall("./" + NS + tag)
    require(len(rows) == 1, "Missing or duplicate direct TRX element: " + tag)
    return rows[0]


def read_bounded(path, maximum):
    require(maximum >= 0, "Negative evidence read budget")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Evidence is empty or exceeds the bounded reader")
    return raw


def bounded_paths(directory, pattern, maximum):
    paths = []
    for path in directory.rglob(pattern):
        require(len(paths) < maximum, "Too many phase evidence files: " + pattern)
        paths.append(path)
    return paths


def parse_xml(raw):
    text = raw.decode("utf-8-sig", errors="strict")
    require(not re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE), "DTD/entity declarations forbidden")
    return ET.fromstring(text)


def read_json(path):
    return json.loads(read_bounded(path, MAX_JSON_BYTES).decode("utf-8-sig", errors="strict"))


def read_trx(path):
    raw = read_bounded(path, MAX_TRX_BYTES)
    root = parse_xml(raw)
    require(root.tag == NS + "TestRun", "TeamTest2010 TestRun required")
    require(all(isinstance(node.tag, str) and node.tag.startswith(NS) for node in root.iter()), "Mixed or missing TRX namespace")
    return root, hashlib.sha256(raw).hexdigest()


def verify(directory, manifest, phase, exit_code, baseline_directory=None, record_proof=True):
    require(phase in ("baseline", "candidate"), "Unknown phase")
    require(exit_code == (1 if phase == "baseline" else 0), "Wrong phase test exit")
    cases = manifest["baseline"]["cases"] if phase == "baseline" else manifest["candidate"]
    count = 16 if phase == "baseline" else 108
    require(len(cases) == count and len({case["name"] for case in cases}) == count, "Frozen roster cardinality")
    require(manifest["expectedCandidateCases"] == 108 and manifest["expectedCandidateMethods"] == 13, "Candidate manifest cardinality")
    require(manifest["testClass"] == "Legacy.Maliev.ProcurementService.Tests.Integration.PurchaseOrderFileMetadataBindingTests",
            "Wrong frozen test class")
    require((manifest["baseline"]["expectedCases"], manifest["baseline"]["expectedPassed"], manifest["baseline"]["expectedFailed"])
            == (16, 6, 10), "Baseline manifest cardinality")
    expected = {case["name"]: case for case in cases}
    reports = bounded_paths(directory, "*.trx", 1)
    require(len(reports) == 1, "Exactly one separate phase TRX required")
    root, trx_sha = read_trx(reports[0])
    containers = {name: one(root, name) for name in ("TestDefinitions", "TestEntries", "Results", "ResultSummary")}
    summary = containers["ResultSummary"]
    counters = one(summary, "Counters")
    for tag in (*containers, "Counters"):
        require(len(list(root.iter(NS + tag))) == 1, "Nested/duplicate TRX container: " + tag)
    require(summary.get("outcome") == ("Failed" if phase == "baseline" else "Completed"), "Wrong phase summary")
    passed, failed = (6, 10) if phase == "baseline" else (108, 0)
    wanted = {"total": str(count), "executed": str(count), "passed": str(passed), "failed": str(failed),
              **{key: "0" for key in ADVERSE}}
    require(counters.attrib == wanted, "All16 exact phase counters required")
    definitions = containers["TestDefinitions"].findall("./" + NS + "UnitTest")
    entries = containers["TestEntries"].findall("./" + NS + "TestEntry")
    results = containers["Results"].findall("./" + NS + "UnitTestResult")
    for tag, rows in (("UnitTest", definitions), ("TestEntry", entries), ("UnitTestResult", results)):
        require(len(rows) == count == len(list(root.iter(NS + tag))), "Direct/global TRX row cardinality")
    require(len(list(root.iter(NS + "Execution"))) == count, "Extra definition executions")
    require(len(list(root.iter(NS + "TestMethod"))) == count, "Extra definition methods")
    defs = {row.get("id"): row for row in definitions}
    joins = {row.get("testId"): row.get("executionId") for row in entries}
    require(len(defs) == len(joins) == count, "Duplicate phase definition/entry")
    actual, executions, failures, identities = set(), set(), set(), {}
    for row in results:
        name, identity, execution = row.get("testName"), row.get("testId"), row.get("executionId")
        require(name in expected and name not in actual, "Unknown/duplicate test display name")
        require(canonical(identity) and canonical(execution) and execution not in executions, "Invalid/duplicate phase GUID")
        definition = defs.get(identity)
        require(definition is not None and definition.get("name") == name, "Definition/name custody")
        require(one(definition, "Execution").get("id") == execution == joins.get(identity), "Three-way execution join")
        method = one(definition, "TestMethod")
        case = expected[name]
        require(method.get("name") == case["method"]
                and method.get("className", "").split(",")[0] == manifest["testClass"], "Wrong actual method/class")
        outcome = case["expectedOutcome"] if phase == "baseline" else "Passed"
        require(row.get("outcome") == outcome, "Unexpected actual case outcome")
        errors = row.findall(".//" + NS + "ErrorInfo")
        if outcome == "Passed":
            require(not errors, "Passing case contains failure evidence")
        else:
            require(len(errors) == 1, "Expected one typed baseline failure")
            message = one(errors[0], "Message").text or ""
            stack = one(errors[0], "StackTrace").text or ""
            require(message == case["expectedMessage"], "Wrong baseline typed chain/path/token/position")
            for frame in manifest["baseline"]["requiredUserFrames"]:
                pattern = (r"^[ \t]*at " + re.escape(manifest["testClass"] + "." + frame["method"])
                           + r"\([^\r\n]*\) in [^\r\n]*[/\\]PurchaseOrderFileMetadataBindingTests\.cs:line "
                           + str(frame["line"]) + r"\r?$")
                require(re.search(pattern, stack, re.MULTILINE), "Missing frozen user conversion/test source frame")
            failures.add(name)
        actual.add(name)
        executions.add(execution)
        identities[name] = identity
    require(actual == set(expected) and len(failures) == failed, "Phase roster/outcomes differ")
    require(len(list(root.iter(NS + "ErrorInfo"))) == failed, "Extra error evidence")
    notice_groups = summary.findall("./" + NS + "RunInfos")
    require(len(notice_groups) <= 1 and len(list(root.iter(NS + "RunInfos"))) == len(notice_groups), "Misplaced/duplicate RunInfos")
    notices = notice_groups[0].findall("./" + NS + "RunInfo") if notice_groups else []
    require(not notice_groups or (not notice_groups[0].attrib and len(notice_groups[0]) == len(notices)), "Unexpected RunInfos content")
    require(len(list(root.iter(NS + "RunInfo"))) == len(notices) == failed, "Baseline failure notices must be bijective; candidate notices forbidden")
    noticed = set()
    for notice in notices:
        require(set(notice.attrib) == {"computerName", "outcome", "timestamp"}
                and notice.get("outcome") == "Error" and bool(notice.get("computerName", "").strip()), "Malformed run notice")
        stamp = notice.get("timestamp", "")
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,7}(?:Z|[+-]\d{2}:\d{2})", stamp), "Unzoned run notice")
        require(datetime.datetime.fromisoformat(stamp).tzinfo is not None, "Unzoned run notice")
        text = one(notice, "Text")
        require(len(notice) == 1 and not text.attrib and not len(text), "Unexpected notice content")
        match = re.fullmatch(r"\[xUnit\.net \d{2}:\d{2}:\d{2}\.\d{2}\]     (.+) \[FAIL\]", text.text or "")
        require(match is not None and match.group(1) in failures and match.group(1) not in noticed, "Unmapped/duplicate failure notice")
        noticed.add(match.group(1))
    require(noticed == failures, "Missing expected baseline notice")
    coverage = bounded_paths(directory, "coverage.cobertura.xml", MAX_COVERAGE_FILES)
    require(bool(coverage), "Missing raw phase coverage")
    remaining, digests, nonempty = MAX_COVERAGE_TOTAL_BYTES, set(), False
    for index, path in enumerate(coverage):
        raw = read_bounded(path, min(MAX_COVERAGE_FILE_BYTES, remaining))
        remaining -= len(raw)
        digests.add(hashlib.sha256(raw).hexdigest())
        if index == 0:
            nonempty = bool(parse_xml(raw).findall("./packages/package/classes/class/lines/line"))
    require(len(digests) == 1 and nonempty, "Empty or inconsistent raw phase coverage")
    if phase == "candidate":
        require(baseline_directory is not None, "Candidate requires bound actual baseline evidence")
        retained = read_json(baseline_directory / "file-metadata-binding-proof.json")
        baseline = verify(baseline_directory, manifest, "baseline", 1, record_proof=False)
        require(retained == baseline, "Retained baseline proof differs from revalidated raw evidence")
        baseline_reports = bounded_paths(baseline_directory, "*.trx", 1)
        require(len(baseline_reports) == 1 and hashlib.sha256(read_bounded(baseline_reports[0], MAX_TRX_BYTES)).hexdigest() == baseline["trxSha256"],
                "Baseline proof is detached from actual raw TRX")
        require(set(baseline["identities"]) == {case["name"] for case in manifest["baseline"]["cases"]}, "Wrong baseline identity subset")
        require(all(identities[name] == identity for name, identity in baseline["identities"].items()),
                "Same harness baseline/candidate test IDs differ")
    proof = {"phase": phase, "passed": passed, "failed": failed, "skipped": 0, "identities": identities,
             "trxSha256": trx_sha, "rawCoverageSha256": next(iter(digests)), "rawCopies": len(coverage),
             "fullSuiteAcceptance": False, "wholeSourceModelParity": False, "productionEnrollmentProven": False}
    if record_proof:
        output = directory / "file-metadata-binding-proof.json"
        if output.exists():
            require(read_json(output) == proof, "Refuse to overwrite a different retained proof")
        else:
            output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    path, phase, exit_code = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    contract = read_json(pathlib.Path("docs/procurement-file-metadata-binding-contract.json"))
    prior = pathlib.Path(sys.argv[4]) if len(sys.argv) == 5 else None
    proof = verify(path, contract, phase, exit_code, prior)
    print(json.dumps({key: proof[key] for key in ("phase", "passed", "failed", "skipped")}))
