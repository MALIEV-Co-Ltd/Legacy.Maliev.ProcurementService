"""Verify hosted individual sort cases; no local .NET execution."""
import collections
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

expected = {
    "EightNullableBranches_SourceNullPlacementAndStableTiesThroughNamedAndNumericHttp":16,
    "NullableSort_StableIdentifierTiePrecedesPagingAndKeepsMetadata":4,
    "SortedRead_AnonymousOrWrongPermissionCannotDiscloseOrMutateMasters":4,
}
root = pathlib.Path(sys.argv[1])
reports = list(root.rglob("*.trx"))
if len(reports) != 1:
    raise SystemExit("Require exactly one actual sort TRX")
ns = {"t":"http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
document = ET.parse(reports[0])
results = document.findall("./t:Results/t:UnitTestResult", ns)
actual = collections.Counter()
for result in results:
    matches = [method for method in expected if
               f"ProcurementNullableSortSourceTests.{method}" in result.get("testName", "")]
    if len(matches) != 1 or result.get("outcome") != "Passed":
        raise SystemExit("Unknown or non-passing sort case")
    actual[matches[0]] += 1
if dict(actual) != expected:
    raise SystemExit(f"Sort cardinality mismatch: {dict(actual)}")
counters = document.find("./t:ResultSummary/t:Counters", ns)
if counters is None or any(int(counters.get(key, "-1")) != 24 for key in ("total", "executed", "passed")):
    raise SystemExit("Require exactly24 executed/passed cases")
if any(int(counters.get(key, "0")) != 0 for key in
       ("failed", "error", "timeout", "aborted", "inconclusive", "notExecuted")):
    raise SystemExit("Failed or skipped sort case")
coverage = list(root.rglob("coverage.cobertura.xml"))
digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in coverage}
if len(digests) != 1:
    raise SystemExit("Require one unique raw coverage report")
packages = ET.parse(coverage[0]).findall("./packages/package")
for assembly in ("Api", "Application", "Data", "Domain"):
    selected = [package for package in packages if package.get("name") == "Legacy.Maliev.ProcurementService." + assembly]
    if not selected or not any(package.findall(".//line") for package in selected):
        raise SystemExit(f"Missing owned executable inventory: {assembly}")
proof = {"passed":24,"failed":0,"skipped":0,"methods":dict(actual),
         "trxSha256":hashlib.sha256(reports[0].read_bytes()).hexdigest(),
         "rawSha256":next(iter(digests)),"rawCopies":len(coverage),"exclusions":[],
         "fullServiceCoverageAcceptance":False,"actualAuthProducerAcceptance":False,
         "note":"Focused sort proof only; master snapshots do not claim all child tables or global collation. Full coverage and actual Auth join remain separate."}
(root / "nullable-sort-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
print(json.dumps(proof, indent=2))
