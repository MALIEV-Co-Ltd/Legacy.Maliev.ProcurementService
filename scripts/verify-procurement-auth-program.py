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
MANIFEST = ROOT / "tools/ProcurementAuthProgram.Tests/public-graph-header-contact-ignored-fields.json"
HISTORICAL_PATH = "tools/ProcurementAuthProgram.Tests/public-graph.json"
HISTORICAL_SHA256 = "205063c79697948343ba659b13757b68ef4814d1b62861484a1dd90c0b8e7d41"
PREVIOUS_ACCEPTED_PATH = "tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json"
PREVIOUS_ACCEPTED_SHA256 = "d4aab5b24027fb666b8571c67450c59cd6b188970b34818fa308b34e215edd1a"
PROJECTS = tuple("Legacy.Maliev.ProcurementService." + part for part in ("Api", "Application", "Data", "Domain"))
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
JOIN_TEST_PROJECT = "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"
PATTERNS = ("directory.build.*", "directory.packages.*", "global.json", "nuget.config", "*.slnx")


def tracked_inputs(repository):
    raw = subprocess.check_output(["git", "-C", str(repository), "ls-tree", "-r", "-z", "HEAD"])
    selected = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if path in (FIXTURE, JOIN_TEST_PROJECT) or any(path.startswith(project + "/") for project in PROJECTS) or (
            "/" not in path and any(fnmatch.fnmatchcase(path.lower(), pattern) for pattern in PATTERNS)
        ):
            selected[path] = metadata.decode("ascii")
    return selected


def require_equal(current, reviewed):
    if current != reviewed or FIXTURE not in reviewed or JOIN_TEST_PROJECT not in reviewed or any(
        not any(path.startswith(project + "/") for path in reviewed) for project in PROJECTS
    ):
        raise ValueError("Runtime/build/public fixture drift requires a separately reviewed graph")


def require_source_change(reviewed, manifest):
    change = manifest["intentionalSourceChanges"]
    changes = change["changedInputs"]
    if reviewed != change["reviewedInputs"]:
        raise ValueError("Runtime/build/public fixture inputs differ from the exact successor inventory")
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


def require_previous_metadata_graph(manifest):
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
    supplier_custody = manifest["latestAcceptedSupplierGraph"]
    supplier_path = "tools/ProcurementAuthProgram.Tests/public-graph-supplier-address.json"
    supplier_sha = "15aefdb6d7d587b3ca9c6c9183f732dc85ab8df0974a8b6ab1f416f7adc73177"
    supplier_bytes = (ROOT / supplier_path).read_bytes()
    if supplier_custody["path"] != supplier_path or supplier_custody["sha256"] != supplier_sha or hashlib.sha256(supplier_bytes).hexdigest() != supplier_sha:
        raise ValueError("Accepted supplier-address65 graph custody must remain exact")
    supplier_graph = json.loads(supplier_bytes)
    if supplier_custody["procurement"] != "574b3b6ccecb4e4df9c4e72c326d9fb7f9a918f5" or supplier_custody["inputCount"] != 65 or supplier_graph["intentionalSourceChanges"]["inputCount"] != 65:
        raise ValueError("Accepted supplier-address65 witness must remain exact")
    bucket_custody = manifest["latestAcceptedBucketGraph"]
    bucket_path = "tools/ProcurementAuthProgram.Tests/public-graph-file-bucket.json"
    bucket_sha = "d5890949f9f397c16fc3ca225993946f9abf8efef866c20e82653210724884a8"
    bucket_bytes = (ROOT / bucket_path).read_bytes()
    if bucket_custody["path"] != bucket_path or bucket_custody["sha256"] != bucket_sha or hashlib.sha256(bucket_bytes).hexdigest() != bucket_sha:
        raise ValueError("Accepted bucket66 graph custody must remain exact")
    bucket_graph = json.loads(bucket_bytes)
    if bucket_custody["procurement"] != "232211084ce15682391036fbbbe777c6c723e773" or bucket_custody["inputCount"] != 66 or bucket_graph["intentionalSourceChanges"]["inputCount"] != 66:
        raise ValueError("Accepted bucket66 witness must remain exact")
    address_custody = manifest["latestAcceptedPurchaseOrderAddressGraph"]
    address_path = "tools/ProcurementAuthProgram.Tests/public-graph-purchase-order-address.json"
    address_sha = "9a4334ef83b14ac2e20fca23599ad2e86cbcacdb2e216d2bf40420b37c96c97f"
    with (ROOT / address_path).open("rb") as stream:
        address_bytes = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(address_bytes) <= 2 * 1024 * 1024:
        raise ValueError("Accepted purchase-order address/header69 witness exceeds the bounded reader")
    if address_custody["path"] != address_path or address_custody["sha256"] != address_sha or hashlib.sha256(address_bytes).hexdigest() != address_sha:
        raise ValueError("Accepted purchase-order address/header69 graph custody must remain exact")
    address_graph = json.loads(address_bytes)
    address_pin = next(entry["commit"] for entry in address_graph["references"] if entry["repository"] == "Legacy.Maliev.ProcurementService")
    if address_custody["procurement"] != "abcbd59573d615642777a74564e348167016dc97" or address_pin != address_custody["procurement"] or address_custody["inputCount"] != 69 or address_graph["intentionalSourceChanges"]["inputCount"] != 69:
        raise ValueError("Accepted purchase-order address/header69 witness must remain exact")
    metadata_custody = manifest["latestAcceptedFileMetadataGraph"]
    metadata_path = "tools/ProcurementAuthProgram.Tests/public-graph-file-metadata-binding.json"
    metadata_sha = "47c06849201f62ac58d01da3043eebe0e07a2b6ba64b20c586fee882d3dee1dd"
    with (ROOT / metadata_path).open("rb") as stream:
        metadata_bytes = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(metadata_bytes) <= 2 * 1024 * 1024:
        raise ValueError("Accepted file-metadata70 witness exceeds the bounded reader")
    if metadata_custody["path"] != metadata_path or metadata_custody["sha256"] != metadata_sha or hashlib.sha256(metadata_bytes).hexdigest() != metadata_sha:
        raise ValueError("Accepted file-metadata70 graph custody must remain exact")
    metadata_graph = json.loads(metadata_bytes)
    metadata_pin = next(entry["commit"] for entry in metadata_graph["references"] if entry["repository"] == "Legacy.Maliev.ProcurementService")
    if metadata_custody["procurement"] != "effa0ffbe129c29bbb5ac2a974b15eed63f07464" or metadata_pin != metadata_custody["procurement"] or metadata_custody["inputCount"] != 70 or metadata_graph["intentionalSourceChanges"]["inputCount"] != 70:
        raise ValueError("Accepted file-metadata70 witness must remain exact")
    identity_custody = manifest["latestAcceptedSupplierIdentityGraph"]
    identity_path = "tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-identity.json"
    identity_sha = "af852115e36d3c8bc9f2b4b38f3b5287cd85aaeaaa8f6bc8b52bb4393c72793b"
    with (ROOT / identity_path).open("rb") as stream:
        identity_bytes = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(identity_bytes) <= 2 * 1024 * 1024:
        raise ValueError("Accepted supplier ignored-identity71 witness exceeds the bounded reader")
    if (identity_custody["path"] != identity_path or identity_custody["sha256"] != identity_sha
            or identity_custody["gitBlob"] != "dd16549fda20264df88d58ea201ba8cad98c0daf"
            or hashlib.sha256(identity_bytes).hexdigest() != identity_sha):
        raise ValueError("Accepted supplier ignored-identity71 graph custody must remain exact")
    identity_graph = json.loads(identity_bytes)
    identity_pin = next(entry["commit"] for entry in identity_graph["references"] if entry["repository"] == "Legacy.Maliev.ProcurementService")
    if (identity_custody["procurement"] != "f7f6930a84278c50f878898169123fe7641211ac"
            or identity_pin != identity_custody["procurement"] or identity_custody["inputCount"] != 71
            or identity_graph["intentionalSourceChanges"]["inputCount"] != 71):
        raise ValueError("Accepted supplier ignored-identity71 witness must remain exact")
    change = manifest["intentionalSourceChanges"]
    paths = {"Legacy.Maliev.ProcurementService.Api/Program.cs",
             "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs",
             "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs"}
    previous_inputs = identity_graph["intentionalSourceChanges"]["reviewedInputs"]
    if (change["previousProcurement"] != identity_pin or change["inputCount"] != 72
            or change["unchangedInputCount"] != 69 or set(change["changedInputs"]) != paths):
        raise ValueError("Metadata identity successor must retain the exact reviewed72/3/69 source envelope")
    for path, binding in change["changedInputs"].items():
        if binding["previousMetadata"] != previous_inputs.get(path):
            raise ValueError("Reviewed source delta is detached from the exact supplier71 preimage")
    for path, metadata in change["reviewedInputs"].items():
        if path not in paths and previous_inputs.get(path) != metadata:
            raise ValueError("Unrelated runtime tuple differs from accepted supplier71 witness")
    procurement_pins = [entry["commit"] for entry in manifest["references"]
                        if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    if (procurement_pins != ["56a6b8d8576b71cfd8e76216118684839c8ea102"]
            or change["reviewedProcurement"] != "56a6b8d8576b71cfd8e76216118684839c8ea102"
            or change["reviewedTree"] != "e057fa74e29f01793b1fd9893435d34a44a90dff"):
        raise ValueError("Auth successor must use the exact newly reviewed native-options producer")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"] if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (external(manifest) != external(historical) or external(manifest) != external(identity_graph)
            or manifest["expectedCases"] != historical["expectedCases"] or manifest["expectedCases"] != identity_graph["expectedCases"]
            or manifest["expectedMethods"] != historical["expectedMethods"] or manifest["expectedMethods"] != identity_graph["expectedMethods"]):
        raise ValueError("External producer pins and actual Auth execution identities must remain unchanged")
    if any(manifest[field] is not False for field in ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Source custody does not qualify production authority or whole-source closure")


def require_historical_graph(manifest):
    custody = manifest["latestAcceptedMetadataIdentityGraph"]
    path = "tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-identity.json"
    digest = "3ebc8ce7a0a5ba574a59ce17d7d0799886eecb02ce4c59dae9f8d74b671d2f2e"
    with (ROOT / path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Accepted metadata-identity72 witness exceeds bounded reader")
    if (set(custody) != {"path", "sha256", "gitBlob", "procurement", "inputCount"}
            or custody["path"] != path or custody["sha256"] != digest
            or custody["gitBlob"] != "d5ec8073e418e461e61e0fffc5dda47318b95861"
            or custody["procurement"] != "56a6b8d8576b71cfd8e76216118684839c8ea102"
            or custody["inputCount"] != 72 or hashlib.sha256(raw).hexdigest() != digest):
        raise ValueError("Accepted metadata-identity72 witness custody must remain exact")
    previous = json.loads(raw)
    require_previous_metadata_graph(previous)
    for field in ("historicalGraph", "previousAcceptedGraph", "latestAcceptedSupplierGraph",
                  "latestAcceptedBucketGraph", "latestAcceptedPurchaseOrderAddressGraph",
                  "latestAcceptedFileMetadataGraph", "latestAcceptedSupplierIdentityGraph"):
        if manifest[field] != previous[field]:
            raise ValueError("Retained historical witness must remain exact: " + field)
    if manifest["previousMetadataIdentityIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous metadata-identity72 source envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    paths = {"Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs",
             "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"}
    if (change["previousProcurement"] != custody["procurement"]
            or change["acceptedBase"] != "44c79ed24c142883563e037bbb5be724ea87322a"
            or change["inputCount"] != 72 or change["unchangedInputCount"] != 70
            or set(change["changedInputs"]) != paths):
        raise ValueError("Header successor requires exact72/2/70 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    if set(change["reviewedInputs"]) != set(previous_inputs):
        raise ValueError("Header successor cannot add or remove runtime/build/fixture inputs")
    for path, binding in change["changedInputs"].items():
        if binding["previousMetadata"] != previous_inputs[path]:
            raise ValueError("Header source delta is detached from exact metadata72 preimage")
    for path, metadata in change["reviewedInputs"].items():
        if path not in paths and previous_inputs[path] != metadata:
            raise ValueError("Unrelated runtime tuple differs from accepted metadata72")
    pins = [entry["commit"] for entry in manifest["references"]
            if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    if (pins != ["4f655c9394c20e5968d8bf6f1d77fdba3f77c7f4"]
            or change["reviewedProcurement"] != "4f655c9394c20e5968d8bf6f1d77fdba3f77c7f4"
            or change["reviewedTree"] != "00c881d326b1db9daff8be047e5e078f14ee9ade"):
        raise ValueError("Header Auth successor requires exact independently reviewed producer")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"]
                              if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (external(manifest) != external(previous)
            or manifest["expectedCases"] != previous["expectedCases"]
            or manifest["expectedMethods"] != previous["expectedMethods"]):
        raise ValueError("External pins and all actual15 Auth identities must remain unchanged")
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Header custody does not qualify production authority or whole-source closure")


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
