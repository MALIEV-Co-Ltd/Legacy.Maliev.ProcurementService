"""Require all normal Procurement deadline regression executions and retained raw evidence."""
import collections
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

expected = {
    "SharedDeadline_DeniesThenRetriesWithoutCachingLateResult": 3,
    "CallerCancellation_PreservesCoalescingCacheAndFreshLiveWrite": 1,
    "LocalAdmissionGuard_RejectsShortSecretBeforePrimaryTransport": 1,
    "MalformedAuthorityDiagnostics_DoNotExposeBodySecretOrPrivateOrigin": 1,
}
root = Path(sys.argv[1])
reports = list(root.rglob("*.trx"))
if len(reports) != 1:
    raise SystemExit("Require one actual deadline TRX")
document = ET.parse(reports[0])
results = document.findall(".//{*}UnitTestResult")
actual = collections.Counter()
for result in results:
    matches = [method for method in expected if
               "ProcurementDefaultsOwnerDeadlineTests." + method in result.get("testName", "")]
    if len(matches) != 1 or result.get("outcome") != "Passed":
        raise SystemExit("Unexpected or non-passing deadline execution")
    actual[matches[0]] += 1
if dict(actual) != expected:
    raise SystemExit("Deadline execution names/cardinality differ")
counters = document.find(".//{*}Counters")
if counters is None or any(int(counters.get(key, "-1")) != 6 for key in ("total", "executed", "passed")):
    raise SystemExit("Require exactly six executed/passed cases")
if any(int(counters.get(key, "0")) for key in
       ("failed", "error", "timeout", "aborted", "inconclusive", "notExecuted", "notRunnable")):
    raise SystemExit("Failure or skip in deadline regressions")
raw = list(root.rglob("coverage.cobertura.xml"))
digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in raw}
if len(digests) != 1:
    raise SystemExit("Require one unique retained raw deadline report")
packages = ET.parse(raw[0]).findall("./packages/package")
for part in ("Api", "Application", "Data", "Domain"):
    assembly = "Legacy.Maliev.ProcurementService." + part
    if not any(p.get("name") == assembly and p.findall(".//line") for p in packages):
        raise SystemExit("Missing actual assembly executable inventory: " + assembly)
receipt = {"passed": 6, "failed": 0, "skipped": 0, "methods": dict(actual),
           "trx_sha256": hashlib.sha256(reports[0].read_bytes()).hexdigest(),
           "raw_sha256": next(iter(digests)), "raw_copies": len(raw),
           "note": "Focused evidence only; all four service assemblies require the separate full-suite80% gate."}
(root / "deadline-proof.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
