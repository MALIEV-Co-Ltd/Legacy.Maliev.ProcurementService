"""Require exact producers, unchanged runtime/fixture inputs, and individual joined passes."""
import collections
import fnmatch
import hashlib
from procurement_address_null_consumer import address_consumer_inputs, supplier_mutation_consumer_inputs
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/ProcurementAuthProgram.Tests/public-graph-supplier-omitted-size.json"
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


def require_consumer_binding(manifest):
    expected = json.loads('{"sourceBase":"75482b3aa7423024bf7443d6131fdbee925f069d","producerCommit":"e45300a59be9804775761bd3ba7826406da534d8","inputCount":74,"changedInputs":{"Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs":{"previousMetadata":"100644 blob f7549641da035088c553d07e42202c73ea881512","reviewedMetadata":"100644 blob aa83c9ddc65ccac0bfc90974f64a817ad8cbbc68"},"Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs":{"previousMetadata":"100644 blob 4a4a10f303c0ea3345c864330b0e2fa9ae7bbc14","reviewedMetadata":"100644 blob 28204fc1402f836d1da3ae94542bb5ce249b1c1b"}},"unchangedInputCount":72,"unchangedInputSha256":"8b6ab924bb164895e958f297de204214b27a9ee44d97865906ddd3d6b6054bfd","producerHarness":{"path":"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs","gitBlob":"d64f561c450d565dafb3bb076b9c1dacbb423570"},"consumerHarness":{"path":"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs","gitBlob":"e29fcc568be0d5b378c9a941484f9bda26d64b31"}}')
    if manifest.get("supplierExplicitSizeConsumer") != expected or manifest["supplierOmittedSizeHarness"] != expected["consumerHarness"]:
        raise ValueError("Supplier explicit-size consumer requires the exact reviewed custody")
    return expected


def observation_consumer_inputs(previous):
    # Issue84 source2f60: current consumer only; every frozen producer/graph remains unchanged.
    program = "Legacy.Maliev.ProcurementService.Api/Program.cs"
    if previous.get(program) != "100644 blob 70310b7db68e08366ee3c723211cdd3910c03f9f":
        raise ValueError("Reviewed observation consumer Program preimage differs")
    current = dict(previous)
    current[program] = "100644 blob a82fb0b60ca92d2df1a39a3b82eaecdeef1f7505"
    return current


def require_consumer_inputs(current, producer, manifest):
    binding = require_consumer_binding(manifest)
    require_source_change(producer, manifest)
    expected = dict(producer)
    for path, change in binding["changedInputs"].items():
        if expected.get(path) != change["previousMetadata"]:
            raise ValueError("Supplier explicit-size producer preimage differs")
        expected[path] = change["reviewedMetadata"]
    unchanged = {path: metadata for path, metadata in producer.items() if path not in binding["changedInputs"]}
    digest = hashlib.sha256(json.dumps(unchanged, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if len(producer) != binding["inputCount"] or len(unchanged) != binding["unchangedInputCount"] or digest != binding["unchangedInputSha256"]:
        raise ValueError("Supplier explicit-size retained inventory differs")
    require_equal(current, supplier_mutation_consumer_inputs(address_consumer_inputs(observation_consumer_inputs(expected))))


def require_harness_custody(local, producer, manifest):
    binding = require_consumer_binding(manifest)
    if (local.resolve() != ROOT.resolve()
            or producer.resolve() != (ROOT / ".joined-public/Legacy.Maliev.ProcurementService").resolve()
            or local.resolve() == producer.resolve()):
        raise ValueError("Supplier harness roots differ from the owned join")
    head = subprocess.check_output(["git", "-C", str(producer), "rev-parse", "HEAD"], text=True, timeout=15).strip()
    if head != binding["producerCommit"]:
        raise ValueError("Supplier immutable producer HEAD differs")
    for repository, harness in ((local, binding["consumerHarness"]), (producer, binding["producerHarness"])):
        for arguments in (("rev-parse", "HEAD:" + harness["path"]), ("hash-object", harness["path"])):
            actual = subprocess.check_output(["git", "-C", str(repository), *arguments], text=True, timeout=15).strip()
            if actual != harness["gitBlob"]:
                raise ValueError("Exact Supplier per-root harness differs")


def inputs(root, manifest):
    require_historical_graph(manifest)
    for entry in manifest["references"]:
        repository, expected = entry["repository"], entry["commit"]
        actual = subprocess.check_output(["git", "-C", str(root / repository), "rev-parse", "HEAD"], text=True).strip()
        if actual != expected:
            raise ValueError("Producer checkout does not equal the immutable graph pin: " + repository)
    producer = root / "Legacy.Maliev.ProcurementService"
    reviewed = tracked_inputs(producer)
    require_consumer_inputs(tracked_inputs(ROOT), reviewed, manifest)
    require_harness_custody(ROOT, producer, manifest)
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


def require_previous_header_graph(manifest):
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


def require_previous_supplier_audit_graph(manifest):
    custody = manifest["latestAcceptedHeaderContactGraph"]
    path = "tools/ProcurementAuthProgram.Tests/public-graph-header-contact-ignored-fields.json"
    digest = "53ab8da5c591279c47233bf1e1c6ce26f90fa2e28f2744b81148bd20c632c90d"
    with (ROOT / path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Accepted header-contact72 witness exceeds bounded reader")
    if (set(custody) != {"path", "sha256", "gitBlob", "procurement", "inputCount", "acceptedMain", "acceptedReceipt"}
            or custody["path"] != path or custody["sha256"] != digest
            or custody["gitBlob"] != "8abb62f1d27efba94f2b54395e3bbda77a9a786e"
            or custody["procurement"] != "4f655c9394c20e5968d8bf6f1d77fdba3f77c7f4"
            or custody["inputCount"] != 72
            or custody["acceptedMain"] != "1ab8e59d4941ba9caad9c50ca67ad54b2ddf6b79"
            or custody["acceptedReceipt"] != "ac486eabf27e3e8c86e41b45327d2bc628a8319f"
            or hashlib.sha256(raw).hexdigest() != digest):
        raise ValueError("Accepted header-contact72 source custody must remain exact")
    previous = json.loads(raw)
    require_previous_header_graph(previous)
    for field in previous:
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != previous[field]:
            raise ValueError("Retained previous header witness differs: " + field)
    if manifest["previousHeaderContactIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous header-contact72/2/70 source envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    paths = {"Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"}
    if (change["previousProcurement"] != custody["procurement"]
            or change["acceptedBase"] != "1ab8e59d4941ba9caad9c50ca67ad54b2ddf6b79"
            or change["inputCount"] != 72 or change["unchangedInputCount"] != 71
            or set(change["changedInputs"]) != paths):
        raise ValueError("Supplier audit successor requires exact72/1/71 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    if set(change["reviewedInputs"]) != set(previous_inputs):
        raise ValueError("Supplier audit successor cannot add or remove runtime/build/fixture inputs")
    for path, binding in change["changedInputs"].items():
        if binding["previousMetadata"] != previous_inputs[path]:
            raise ValueError("Supplier audit delta is detached from accepted header72 preimage")
    for path, metadata in change["reviewedInputs"].items():
        if path not in paths and previous_inputs[path] != metadata:
            raise ValueError("Unrelated runtime tuple differs from accepted header72")
    pins = [entry["commit"] for entry in manifest["references"]
            if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    if (pins != ["d159befd91d7bed196d045366870b5bb60c21725"] or change["reviewedProcurement"] != "d159befd91d7bed196d045366870b5bb60c21725"
            or change["reviewedTree"] != "f06d1cfa91352338b48aedd9cffae3b9d500c7e8"):
        raise ValueError("Supplier audit Auth successor requires exact independently reviewed producer")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"]
                              if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (external(manifest) != external(previous) or manifest["expectedCases"] != previous["expectedCases"]
            or manifest["expectedMethods"] != previous["expectedMethods"]):
        raise ValueError("External pins and all actual15 Auth identities must remain unchanged")
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Supplier audit custody does not qualify production or whole-source closure")


def require_previous_metadata_audit_graph(manifest):
    custody = manifest["latestAcceptedSupplierAuditGraph"]
    path = "tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-audits.json"
    digest = "a97f8ef186e665d0e9610fcdbfc566172bc7038f6d7b82897ddfa21b52798057"
    with (ROOT / path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Accepted Supplier audit72 witness exceeds bounded reader")
    if (set(custody) != {"path", "sha256", "gitBlob", "procurement", "inputCount", "acceptedMain", "acceptedReceipt"}
            or custody["path"] != path or custody["sha256"] != digest
            or custody["gitBlob"] != "45dd7bd104ef039c58eed5ce19b7ef81de2b9e20"
            or custody["procurement"] != "d159befd91d7bed196d045366870b5bb60c21725"
            or custody["inputCount"] != 72
            or custody["acceptedMain"] != "665f796eab8a6eea37fd1189d3c0821fc1dc5fa9"
            or custody["acceptedReceipt"] != "4d284e6fea883d01d47e4fa58b64e22ad5b3fbb8"
            or hashlib.sha256(raw).hexdigest() != digest):
        raise ValueError("Accepted Supplier audit72 source custody must remain exact")
    previous = json.loads(raw)
    require_previous_supplier_audit_graph(previous)
    for field in previous:
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != previous[field]:
            raise ValueError("Retained previous Supplier audit witness differs: " + field)
    if manifest["previousSupplierAuditIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous Supplier audit72/1/71 source envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    metadata = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
    paths = {metadata}
    if (change["previousProcurement"] != custody["procurement"]
            or change["acceptedBase"] != "665f796eab8a6eea37fd1189d3c0821fc1dc5fa9"
            or change["inputCount"] != 72 or change["unchangedInputCount"] != 71
            or set(change["changedInputs"]) != paths):
        raise ValueError("Metadata audit successor requires exact72/1/71 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    if set(change["reviewedInputs"]) != set(previous_inputs):
        raise ValueError("Metadata audit successor cannot add or remove runtime/build/fixture inputs")
    binding = change["changedInputs"][metadata]
    if (set(binding) != {"previousMetadata", "reviewedMetadata"}
            or binding["previousMetadata"] != previous_inputs[metadata]
            or binding["previousMetadata"] != "100644 blob be119d54a90a0772444b9f61f97be53a779610ba"
            or binding["reviewedMetadata"] != "100644 blob 2646aec8eb8e6ff44e48b52b7a47fed5b4a6fac2"
            or change["reviewedInputs"][metadata] != binding["reviewedMetadata"]):
        raise ValueError("Metadata audit delta detached from accepted Supplier72 preimage/postimage")
    for path, value in change["reviewedInputs"].items():
        if path not in paths and previous_inputs[path] != value:
            raise ValueError("Unrelated runtime tuple differs from accepted Supplier audit72")
    pins = [entry["commit"] for entry in manifest["references"]
            if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    if (pins != ["22e307d936993c2976d8f64819d37c5035b4b1de"] or change["reviewedProcurement"] != "22e307d936993c2976d8f64819d37c5035b4b1de"
            or change["reviewedTree"] != "087b3378c8491c701c65b4e8f03f4912b8410630"):
        raise ValueError("Metadata audit Auth successor requires exact independently reviewed producer")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"]
                              if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (external(manifest) != external(previous) or manifest["expectedCases"] != previous["expectedCases"]
            or manifest["expectedMethods"] != previous["expectedMethods"]):
        raise ValueError("External pins and all actual15 Auth identities must remain unchanged")
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Metadata audit custody does not qualify production or whole-source closure")


def require_previous_country_id_graph(manifest):
    custody = manifest["latestAcceptedMetadataAuditGraph"]
    path = "tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-audits.json"
    digest = "3ca45a0827fea6653f6fd0e4d3966f363bb013e418fe20e627c82016d0fd6f97"
    with (ROOT / path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Accepted metadata audit72 witness exceeds bounded reader")
    if (set(custody) != {"path", "sha256", "gitBlob", "procurement", "inputCount", "acceptedMain", "acceptedReceipt"}
            or custody["path"] != path or custody["sha256"] != digest
            or custody["gitBlob"] != "8bec326c5639c6c437abbb3926bf2000bd3ddd8e"
            or custody["procurement"] != "22e307d936993c2976d8f64819d37c5035b4b1de"
            or custody["inputCount"] != 72
            or custody["acceptedMain"] != "797d872a243d5d4be4939c37fa648ecfcee459ac"
            or custody["acceptedReceipt"] != "17f6ed69f945a2e0410b249ba116c38f8c6cdd81"
            or hashlib.sha256(raw).hexdigest() != digest):
        raise ValueError("Accepted metadata audit72 source custody must remain exact")
    previous = json.loads(raw)
    require_previous_metadata_audit_graph(previous)
    for field in previous:
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != previous[field]:
            raise ValueError("Retained previous metadata audit witness differs: " + field)
    if manifest["previousMetadataAuditIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous metadata audit72/1/71 source envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    metadata = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
    paths = {metadata}
    if (change["previousProcurement"] != custody["procurement"]
            or change["acceptedBase"] != "797d872a243d5d4be4939c37fa648ecfcee459ac"
            or change["inputCount"] != 72 or change["unchangedInputCount"] != 71
            or set(change["changedInputs"]) != paths):
        raise ValueError("Address country successor requires exact72/1/71 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    if set(change["reviewedInputs"]) != set(previous_inputs):
        raise ValueError("Address country successor cannot add or remove runtime/build/fixture inputs")
    binding = change["changedInputs"][metadata]
    if (set(binding) != {"previousMetadata", "reviewedMetadata"}
            or binding["previousMetadata"] != previous_inputs[metadata]
            or binding["previousMetadata"] != "100644 blob 2646aec8eb8e6ff44e48b52b7a47fed5b4a6fac2"
            or binding["reviewedMetadata"] != "100644 blob 112e92787f4c07d47cf0caa404abb392a3d8563b"
            or change["reviewedInputs"][metadata] != binding["reviewedMetadata"]):
        raise ValueError("Address country delta detached from accepted metadata audit preimage/postimage")
    for path, value in change["reviewedInputs"].items():
        if path not in paths and previous_inputs[path] != value:
            raise ValueError("Unrelated runtime tuple differs from accepted metadata audit72")
    pins = [entry["commit"] for entry in manifest["references"]
            if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    if (pins != ["d997f2a527a478110ac3bd96c915f4d0f6ab734a"] or change["reviewedProcurement"] != "d997f2a527a478110ac3bd96c915f4d0f6ab734a"
            or change["reviewedTree"] != "0b15ce62424c15f2ffda7004304939b919888d76"):
        raise ValueError("Address country Auth successor requires exact independently reviewed producer")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"]
                              if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (external(manifest) != external(previous) or manifest["expectedCases"] != previous["expectedCases"]
            or manifest["expectedMethods"] != previous["expectedMethods"]):
        raise ValueError("External pins and all actual15 Auth identities must remain unchanged")
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Address country custody does not qualify production or whole-source closure")


def require_previous_source_body_graph(manifest):
    custody = manifest["latestAcceptedCountryIdGraph"]
    expected_custody = json.loads('{"path":"tools/ProcurementAuthProgram.Tests/public-graph-address-country-id.json","sha256":"4a7deb0c024900377795e20f2b0521cffd0f045913dfbf1f97e05a1bf966e9f3","gitBlob":"e433e128dac8a930b2e8b01f9639ec92f848aa4d","procurement":"d997f2a527a478110ac3bd96c915f4d0f6ab734a","inputCount":72,"acceptedMain":"646055868161c8f19e6b6daa278b01019146ac9a","acceptedReceipt":"5f443a04fbcd41dc003cbb0cd95059c7a5e88bd9"}')
    if custody != expected_custody:
        raise ValueError("Accepted country72 source custody must remain exact")
    with (ROOT / expected_custody["path"]).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_custody["sha256"]:
        raise ValueError("Accepted country72 witness differs or exceeds bounded reader")
    previous = json.loads(raw)
    require_previous_country_id_graph(previous)
    for field in previous:
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != previous[field]:
            raise ValueError("Retained country72 witness differs: " + field)
    if manifest["previousCountryIdIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous country72/1/71 source envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    expected_changes = json.loads('{"Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementSourceBodyInputFormatter.cs":{"previousMetadata":null,"reviewedMetadata":"100644 blob 942a1b8f8f18ea3a9727691a05a784aec688614d"},"Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementOriginalBodyModels.cs":{"previousMetadata":null,"reviewedMetadata":"100644 blob e352494ce31eb5bead53a78cc4c950a7bae3e54e"},"Legacy.Maliev.ProcurementService.Api/Program.cs":{"previousMetadata":"100644 blob 0259b5722072609bb7c356bd1c9a5f49fd2d0caa","reviewedMetadata":"100644 blob 70310b7db68e08366ee3c723211cdd3910c03f9f"},"Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj":{"previousMetadata":"100644 blob bd8fdadcbee41805eedd7a43c6eb8a02099e17d7","reviewedMetadata":"100644 blob 30c131eb10c554b445e878c0b148cbe79d8c7cd3"},"Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj":{"previousMetadata":"100644 blob 69b4ebf74c1a85d0949321360e81105db0f671a6","reviewedMetadata":"100644 blob af7ca6ae938ae85cac598a75852e38863fa6912a"}}')
    if (change["previousProcurement"] != expected_custody["procurement"]
            or change["acceptedBase"] != "646055868161c8f19e6b6daa278b01019146ac9a"
            or change["reviewedProcurement"] != "35b6926e4a7abefa9ef701f4178bd6b3093d9648"
            or change["reviewedTree"] != "273dfa0fadab472a5536079f7cb04231825a16b0"
            or change["inputCount"] != 74 or change["unchangedInputCount"] != 69
            or change["unchangedInputSha256"] != "761b4afe866cfafaec1427a0e073571f974391b4119d4810c6d7fd5bde44fe4f"
            or change["changedInputs"] != expected_changes):
        raise ValueError("Source body successor requires exact74/5/69 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    added = {path for path, binding in expected_changes.items() if binding["previousMetadata"] is None}
    if len(added) != 2 or set(change["reviewedInputs"]) != set(previous_inputs) | added:
        raise ValueError("Source body successor requires exactly two reviewed new runtime inputs")
    for path, binding in expected_changes.items():
        if (previous_inputs.get(path) != binding["previousMetadata"]
                or change["reviewedInputs"][path] != binding["reviewedMetadata"]):
            raise ValueError("Source body delta detached from exact preimage/postimage: " + path)
    for path, value in previous_inputs.items():
        if path not in expected_changes and change["reviewedInputs"][path] != value:
            raise ValueError("Unrelated runtime tuple differs from accepted country72")
    pins = [entry["commit"] for entry in manifest["references"]
            if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"]
                              if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if (pins != ["35b6926e4a7abefa9ef701f4178bd6b3093d9648"] or external(manifest) != external(previous)
            or manifest["expectedCases"] != previous["expectedCases"]
            or manifest["expectedMethods"] != previous["expectedMethods"]):
        raise ValueError("Source body Auth producer, external pins and actual15 identities must remain exact")
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Source body custody does not qualify production or whole-source closure")


def require_historical_graph(manifest):
    previous_path = ROOT / "tools/ProcurementAuthProgram.Tests/public-graph-source-body-input.json"
    with previous_path.open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Retained source-body witness exceeds bounded reader")
    digest = hashlib.sha1(("blob " + str(len(raw)) + "\0").encode() + raw).hexdigest()
    if digest != "0a3573be3d7fa1d08a6071b71ed54449c9a3c578":
        raise ValueError("Retained source-body witness differs")
    previous = json.loads(raw)
    require_previous_source_body_graph(previous)
    for field in previous:
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != previous[field]:
            raise ValueError("Retained source-body witness differs: " + field)
    if manifest["previousSourceBodyIntentionalSourceChanges"] != previous["intentionalSourceChanges"]:
        raise ValueError("Previous source-body74/5/69 envelope must remain exact")
    change = manifest["intentionalSourceChanges"]
    expected_changes = json.loads('{"Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs":{"previousMetadata":"100644 blob 90c2628be1aceef0178533add09fdea7efa4c42a","reviewedMetadata":"100644 blob 7d5f584a13022c56b13e4517748cc772658ba74c"},"Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs":{"previousMetadata":"100644 blob 9b17fd46fce25162e30854210a1f945a1f9d6f48","reviewedMetadata":"100644 blob 4a4a10f303c0ea3345c864330b0e2fa9ae7bbc14"},"Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs":{"previousMetadata":"100644 blob 49461d4f6a13cba8b347001c24920006a5fd5eaf","reviewedMetadata":"100644 blob f116b6f1f0258f2f3bfd0eb35190bd14a64c06f4"}}')
    if (change["previousProcurement"] != "35b6926e4a7abefa9ef701f4178bd6b3093d9648"
            or change["acceptedBase"] != "9e45066ae682b5cbc54975451a8d12c6f432e862"
            or change["reviewedProcurement"] != "e45300a59be9804775761bd3ba7826406da534d8"
            or change["reviewedTree"] != "9d1898c3299fee92d804512deaf88d0f8edaf61d"
            or change["inputCount"] != 74 or change["unchangedInputCount"] != 71
            or change["unchangedInputSha256"] != "944d4b12140f370c6b38a6f8fd81302ce5fe92e7cf6b26ba1c24356ff9f204fe"
            or change["changedInputs"] != expected_changes):
        raise ValueError("Supplier omitted-size successor requires exact74/3/71 source envelope")
    previous_inputs = previous["intentionalSourceChanges"]["reviewedInputs"]
    if set(change["reviewedInputs"]) != set(previous_inputs):
        raise ValueError("Supplier omitted-size successor cannot add or remove compiled inputs")
    for path, value in previous_inputs.items():
        expected = expected_changes[path]["reviewedMetadata"] if path in expected_changes else value
        if change["reviewedInputs"][path] != expected:
            raise ValueError("Supplier omitted-size successor input differs: " + path)
    if manifest["references"] != json.loads('[{"repository":"Legacy.Maliev.AuthService","commit":"b27fbef06a3aa58c1f4fc0e75d7c70b32be76266"},{"repository":"Legacy.Maliev.ServiceDefaults","commit":"ecb05cbbd68717e415f69df2ac488c1d323b1da3"},{"repository":"Legacy.Maliev.CompatibilityContracts","commit":"78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7"},{"repository":"Legacy.Maliev.ProcurementService","commit":"e45300a59be9804775761bd3ba7826406da534d8"}]'):
        raise ValueError("Supplier omitted-size producer and external pins must remain exact")
    if manifest["supplierOmittedSizeHarness"] != json.loads('{"path":"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs","gitBlob":"e29fcc568be0d5b378c9a941484f9bda26d64b31"}'):
        raise ValueError("Supplier omitted-size harness binding differs")
    require_consumer_binding(manifest)
    if any(manifest[field] is not False for field in
           ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Supplier omitted-size custody does not qualify production or whole-source closure")


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
