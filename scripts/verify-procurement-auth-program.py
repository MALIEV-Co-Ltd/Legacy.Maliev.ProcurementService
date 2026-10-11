"""Require exact producers, unchanged runtime/fixture inputs, and individual joined passes."""
import collections
import fnmatch
import hashlib
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/ProcurementAuthProgram.Tests/public-graph-supplier-address.json"
HISTORICAL_PATH = "tools/ProcurementAuthProgram.Tests/public-graph.json"
HISTORICAL_SHA256 = "205063c79697948343ba659b13757b68ef4814d1b62861484a1dd90c0b8e7d41"
PREVIOUS_ACCEPTED_PATH = "tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json"
PREVIOUS_ACCEPTED_SHA256 = "d4aab5b24027fb666b8571c67450c59cd6b188970b34818fa308b34e215edd1a"
PROJECTS = tuple("Legacy.Maliev.ProcurementService." + part for part in ("Api", "Application", "Data", "Domain"))
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
PATTERNS = ("directory.build.*", "directory.packages.*", "global.json", "nuget.config", "*.slnx")


def tracked_inputs(repository):
    raw = subprocess.check_output(["git", "-C", str(repository), "ls-tree", "-r", "-z", "HEAD"])
    selected = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if path == FIXTURE or any(path.startswith(project + "/") for project in PROJECTS) or (
            "/" not in path and any(fnmatch.fnmatchcase(path.lower(), pattern) for pattern in PATTERNS)
        ):
            selected[path] = metadata.decode("ascii")
    return selected


def require_equal(current, reviewed):
    if current != reviewed or FIXTURE not in reviewed or any(
        not any(path.startswith(project + "/") for path in reviewed) for project in PROJECTS
    ):
        raise ValueError("Runtime/build/public fixture drift requires a separately reviewed graph")


def require_source_change(reviewed, manifest):
    change = manifest["intentionalSourceChanges"]
    changes = change["changedInputs"]
    if not changes or len(reviewed) != change["inputCount"]:
        raise ValueError("Missing reviewed changes or runtime input count drift")
    for path, binding in changes.items():
        if path not in reviewed or reviewed[path] != binding["reviewedMetadata"]:
            raise ValueError("Intentional source changes do not match frozen metadata")
    unchanged = {name: metadata for name, metadata in reviewed.items() if name not in changes}
    digest = hashlib.sha256(json.dumps(unchanged, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if len(unchanged) != change["unchangedInputCount"] or digest != change["unchangedInputSha256"]:
        raise ValueError("Unrelated runtime/build/public fixture drift outside reviewed source string changes")


def inputs(root, manifest):
    require_historical_graph(manifest)
    for entry in manifest["references"]:
        repository, expected = entry["repository"], entry["commit"]
        actual = subprocess.check_output(["git", "-C", str(root / repository), "rev-parse", "HEAD"], text=True).strip()
        if actual != expected:
            raise ValueError("Producer checkout does not equal the immutable graph pin: " + repository)
    reviewed = tracked_inputs(root / "Legacy.Maliev.ProcurementService")
    require_equal(tracked_inputs(ROOT), reviewed)
    require_source_change(reviewed, manifest)
    print(json.dumps({"graphId": manifest["graphId"], "references": manifest["references"], "identicalRuntimeBuildFixtureInputs": len(reviewed)}))


def require_historical_graph(manifest):
    custody = manifest["historicalGraph"]
    historical_bytes = (ROOT / HISTORICAL_PATH).read_bytes()
    if custody["path"] != HISTORICAL_PATH or custody["sha256"] != HISTORICAL_SHA256 or hashlib.sha256(historical_bytes).hexdigest() != HISTORICAL_SHA256:
        raise ValueError("Historical frozen graph custody must remain exact")
    historical = json.loads(historical_bytes)
    previous_bytes = (ROOT / PREVIOUS_ACCEPTED_PATH).read_bytes()
    previous_custody = manifest["previousAcceptedGraph"]
    if previous_custody["path"] != PREVIOUS_ACCEPTED_PATH or previous_custody["sha256"] != PREVIOUS_ACCEPTED_SHA256 or hashlib.sha256(previous_bytes).hexdigest() != PREVIOUS_ACCEPTED_SHA256:
        raise ValueError("Accepted child64 graph custody must remain exact")
    previous = json.loads(previous_bytes)
    if previous_custody["inputCount"] != 64 or previous["intentionalSourceChanges"]["inputCount"] != 64 or previous_custody["procurement"] != "99049bab2c100ffdf6606bf11a2f50980c0cf3cf":
        raise ValueError("Previous graph must retain the accepted child64 witness")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"] if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if external(manifest) != external(historical) or manifest["expectedCases"] != historical["expectedCases"] or manifest["expectedMethods"] != historical["expectedMethods"]:
        raise ValueError("External producer pins and actual Auth execution identities must remain unchanged")
    if any(manifest[field] is not False for field in ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Source custody does not qualify production authority or whole-source closure")


def results(root, manifest):
    require_historical_graph(manifest)
    reports = list(root.rglob("*.trx"))
    if len(reports) != 1:
        raise ValueError("Require exactly one join TRX")
    ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
    document = ET.parse(reports[0])
    rows = document.findall("./t:Results/t:UnitTestResult", ns)
    methods = {row.get("id"): row.find("t:TestMethod", ns) for row in document.findall("./t:TestDefinitions/t:UnitTest", ns)}
    actual = collections.Counter()
    for row in rows:
        if row.get("outcome") != "Passed":
            raise ValueError("Every declared join execution must individually pass")
        method = methods[row.get("testId")]
        actual[method.get("className").split(",")[0] + "." + method.get("name")] += 1
    if len(rows) != manifest["expectedCases"] or dict(actual) != manifest["expectedMethods"]:
        raise ValueError("Joined execution names/cardinality differ from the declared graph")
    counters = document.find("./t:ResultSummary/t:Counters", ns).attrib
    if int(counters["passed"]) != len(rows) or int(counters["total"]) != len(rows) or any(
        int(counters.get(key, 0)) for key in ("failed", "error", "timeout", "aborted", "inconclusive", "notExecuted", "notRunnable")
    ):
        raise ValueError("Join counters contain failures/skips/missing executions")
    raw = list(root.rglob("coverage.cobertura.xml"))
    digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in raw}
    if len(digests) != 1:
        raise ValueError("Require one unique retained raw joined coverage report")
    # Package-level line counts are not required by Cobertura; inspect executable lines directly.
    for assembly in ("Legacy.Maliev.AuthService.Api", "Legacy.Maliev.ProcurementService.Api"):
        package = next((p for p in ET.parse(raw[0]).findall("./packages/package") if p.get("name") == assembly), None)
        if package is None or not package.findall("./classes/class/lines/line"):
            raise ValueError("Missing actual producer executable raw lines: " + assembly)
    print(json.dumps({"graphId": manifest["graphId"], "passed": len(rows), "failed": 0, "skipped": 0,
                      "actualMethods": dict(actual), "trxSha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
                      "rawSha256": next(iter(digests)), "rawCopies": len(raw), "exclusions": [],
                      "fullServiceCoverageAcceptance": False, "productionEnrollmentProven": False, "productionIamBridgeProven": False}))


if __name__ == "__main__":
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mode, root = sys.argv[1], pathlib.Path(sys.argv[2])
    if mode == "inputs":
        inputs(root, manifest)
    elif mode == "results":
        results(root, manifest)
    else:
        raise ValueError("Unknown validation mode")
