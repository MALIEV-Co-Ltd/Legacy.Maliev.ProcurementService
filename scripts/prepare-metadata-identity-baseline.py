"""Bind only the new171 harness to accepted9005; require exact source and normal hosted disposal."""
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

BASE = "9005cfbae5e5ef2b5e4267d1700b343256e7a821"
BASE_TREE = "9fe4a4a43c742f04acfd845a435a3618c0e68779"
PROGRAM = "Legacy.Maliev.ProcurementService.Api/Program.cs"
API_PROJECT = "Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj"
CONVERTER = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs"
METADATA_IDENTITY = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
HEADER = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs"
SUPPLIER = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
REPOSITORY = "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
TEST_PROJECT = "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"
TESTS = {"metadata": "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredBodyIdTests.cs"}
SCRIPT_PATHS = {
    "scripts/prepare-metadata-identity-baseline.py",
    "scripts/verify-metadata-identity-results.py",
    "scripts/observe-metadata-identity-providers.py",
    "scripts/test_metadata_identity_results.py",
    "scripts/require-metadata-identity-admission.py",
    ".github/workflows/procurement-metadata-identity.yml",
}
RETIRED_PRODUCER = "2ab0dc07909a8b690597b54262498afb1b0da5f3"
RETIRED_REVIEW_BLOB = "b06528e31494a72f0752e8a853b3b888d4d91a80"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TRX_BYTES = 16 * 1024 * 1024
MAX_PHASE_BYTES = 20 * 1024 * 1024
MAX_OPERATION_BYTES = 96 * 1024 * 1024
SOURCE_FORMATTER = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementSourceBodyInputFormatter.cs"
SOURCE_MODELS = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementOriginalBodyModels.cs"

SUPPLIER_QUERY_RUNTIME = {
    "Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs": "7d5f584a13022c56b13e4517748cc772658ba74c",
    "Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs": "4a4a10f303c0ea3345c864330b0e2fa9ae7bbc14",
    "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs": "f116b6f1f0258f2f3bfd0eb35190bd14a64c06f4",
}
SUPPLIER_QUERY_TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs"
SUPPLIER_QUERY_TEST_BLOB = "d64f561c450d565dafb3bb076b9c1dacbb423570"


def require(value, message):
    if not value:
        raise ValueError(message)


def read_bounded(path, maximum, budget):
    limit = min(maximum, budget[0])
    require(limit >= 0, "Negative source/proof budget")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "Source/proof exceeds actual byte bound")
    budget[0] -= len(raw)
    return raw


def decode_json(raw):
    return json.loads(raw.decode("utf-8-sig", errors="strict"))


def git(root, *args):
    with tempfile.TemporaryFile() as output:
        subprocess.run(["git", "-C", str(root), *args], stdout=output, check=True, timeout=15)
        output.seek(0)
        raw = output.read(4 * 1024 * 1024 + 1)
    require(len(raw) <= 4 * 1024 * 1024, "Git source metadata exceeds actual byte bound")
    return raw


def blob(root, path):
    return git(root, "hash-object", path).decode().strip()


def git_blob_record(value):
    require(isinstance(value, dict) and set(value) == {"gitBlob"}
            and isinstance(value["gitBlob"], str)
            and re.fullmatch(r"[0-9a-f]{40}", value["gitBlob"]) is not None,
            "Require one explicit public Git blob provenance record")
    return value["gitBlob"]


def require_retired_source_custody(manifest):
    retired = manifest["supersededUnpublishedDesign"]
    require(isinstance(retired, dict)
            and set(retired) == {"producer", "authPacket", "status", "bindingFormat"}
            and retired["bindingFormat"] == "git-blob-record-v1"
            and retired["producer"] == RETIRED_PRODUCER
            and git_blob_record(retired["authPacket"]) == RETIRED_REVIEW_BLOB
            and retired["status"] == "HOLD; never publish/reuse Auth pin; Root must create fresh reviewed producer",
            "Retired public source-review custody must remain exact and explicitly typed")


def runtime_bindings(manifest):
    require(manifest.get("runtimeBindingFormat") == "git-blob-record-v1",
            "Require the reviewed Git blob provenance format")
    value = manifest["runtimePostimages"]
    require(isinstance(value, dict) and set(value) == {PROGRAM, API_PROJECT, CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY, SUPPLIER, SOURCE_FORMATTER, SOURCE_MODELS} | set(SUPPLIER_QUERY_RUNTIME),
            "Require exactly the eleven reviewed changed runtime inputs")
    return {path: git_blob_record(record) for path, record in value.items()}


def require_runtime_postimages(candidate, manifest):
    for path, expected in SUPPLIER_QUERY_RUNTIME.items():
        require(git_blob_record(manifest["runtimePostimages"][path]) == expected,
                "Exact Supplier omitted-size runtime successor differs: " + path)
    for path, expected in runtime_bindings(manifest).items():
        require(blob(candidate, path) == expected, "Wrong reviewed runtime postimage: " + path)


def phase_reports(directory):
    found = []
    for path in directory.rglob("*.trx"):
        require(not found, "Multiple phase TRX files")
        found.append(path)
    return found


def require_phase(output, phase, family, budget):
    local = [min(MAX_PHASE_BYTES, budget[0])]
    initial = local[0]
    directory = output / (phase + "-" + family)
    proof_raw = read_bounded(directory / "metadata-identity-proof.json", MAX_JSON_BYTES, local)
    receipt_raw = read_bounded(directory / "provider-observation.json", MAX_JSON_BYTES, local)
    proof, receipt = decode_json(proof_raw), decode_json(receipt_raw)
    wanted = (94, 77, 1) if phase == "baseline" else (171, 0, 0)
    require(type(receipt.get("exitCode")) is int
            and (proof.get("passed"), proof.get("failed"), receipt.get("exitCode")) == wanted
            and proof.get("skipped") == 0 and proof.get("phase") == receipt.get("phase") == phase
            and proof.get("family") == receipt.get("family") == family, "Wrong actual phase/counter/exit receipt")
    require(receipt.get("owningRun") == os.environ.get("GITHUB_RUN_ID")
            and receipt.get("owningAttempt") == os.environ.get("GITHUB_RUN_ATTEMPT"), "Wrong actual receipt custody")
    require(receipt.get("processExited") is True and receipt.get("normalFixtureDisposalProven") is True
            and receipt.get("resourcesAbsent") is True and receipt.get("uncertainResourcesPreserved") is False
            and receipt.get("errors") == [], "Normal fixture/provider disposal not proven")
    cleanup = receipt.get("processSessionCleanup") or {}
    require(cleanup.get("verified") is True and cleanup.get("forcedCleanup") is False
            and cleanup.get("handlesClosed") is True and cleanup.get("launcherExited") is True
            and cleanup.get("remainingSessionMembers") == [] and cleanup.get("cleanupErrors") == [],
            "Process/session cleanup not proven")
    disposal = receipt.get("disposalObservation") or {}
    polls = disposal.get("polls") or []
    require(disposal.get("settled") is True and disposal.get("errors") == [] and bool(polls)
            and polls[-1].get("containerInventoryAvailable") is True
            and polls[-1].get("volumeInventoryAvailable") is True
            and polls[-1].get("remainingContainerIds") == [] and polls[-1].get("remainingVolumeNames") == [],
            "Terminal provider inventories not proven")
    reports = phase_reports(directory)
    require(len(reports) == 1, "One actual phase TRX required")
    trx_raw = read_bounded(reports[0], MAX_TRX_BYTES, local)
    actual = hashlib.sha256(trx_raw).hexdigest()
    require(actual == proof.get("trxSha256") == receipt.get("rawTrxSha256"), "Proof/receipt detached from raw TRX")
    budget[0] -= initial - local[0]
    return {"phase": phase, "family": family, "proofSha256": hashlib.sha256(proof_raw).hexdigest(),
            "receiptSha256": hashlib.sha256(receipt_raw).hexdigest(), "trxSha256": actual, "normalDisposal": True}


def require_script_bindings(candidate, manifest):
    require(set(manifest["scriptBindings"]) == SCRIPT_PATHS, "Wrong exact hosted source/control roster")
    for path, record in manifest["scriptBindings"].items():
        require(blob(candidate, path) == git_blob_record(record)
                == git(candidate, "rev-parse", "HEAD:" + path).decode().strip(),
                "Hosted source/control differs from reviewed HEAD: " + path)


def require_admissions(output, after):
    stages = ["initial", "baseline-build", "baseline-test", "candidate-build", "candidate-test"] if after else ["initial"]
    receipts, stamps = [], []
    for stage in stages:
        raw = read_bounded(output / ("admission-" + stage + ".json"), MAX_JSON_BYTES, [MAX_JSON_BYTES])
        receipt = decode_json(raw)
        require(receipt.get("stage") == stage and receipt.get("passed") is True
                and receipt.get("owningRun") == os.environ.get("GITHUB_RUN_ID")
                and receipt.get("owningAttempt") == os.environ.get("GITHUB_RUN_ATTEMPT")
                and receipt.get("minimumMemAvailableKiB") == 3145728
                and type(receipt.get("memAvailableKiB")) is int and receipt["memAvailableKiB"] >= 3145728
                and receipt.get("workers") == [] and "failureCategory" not in receipt,
                "Required unchanged hosted admission guard/custody failed")
        stamp = datetime.datetime.fromisoformat(receipt["observedAtUtc"])
        require(stamp.tzinfo is not None, "Admission observation must be zoned")
        stamps.append(stamp)
        receipts.append({"stage": stage, "sha256": hashlib.sha256(raw).hexdigest()})
    require(stamps == sorted(stamps), "Admission stage order changed")
    if after:
        for phase, index in (("baseline", 2), ("candidate", 4)):
            observed = decode_json(read_bounded(output / (phase + "-metadata") / "provider-observation.json",
                                               MAX_JSON_BYTES, [MAX_JSON_BYTES]))
            started = datetime.datetime.fromisoformat(observed["startedAtUtc"])
            require(started.tzinfo is not None and stamps[index] <= started,
                    "Test process started before its resource admission")
    return receipts


def require_header_harness_bindings(candidate, manifest):
    bindings = manifest["headerIgnoredFieldHarnesses"]
    expected = {
        "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementHeaderIgnoredFieldsTests.cs",
        "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPurchaseOrderHeaderBindingTests.cs",
        "Legacy.Maliev.ProcurementService.Tests/Data/ProcurementPostgresMigrationTests.cs",
        "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredAuditTests.cs",
        "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredAuditDateTests.cs",
        "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressCountryIdBindingTests.cs",
    }
    require(isinstance(bindings, dict) and set(bindings) == expected, "Wrong reviewed header harness roster")
    for path, record in bindings.items():
        require(blob(candidate, path) == git_blob_record(record), "Reviewed header harness source differs")
    return expected


def prepare(baseline, manifest_path, verify_only=False):
    candidate = pathlib.Path(__file__).resolve().parents[1]
    budget = [MAX_OPERATION_BYTES]
    raw_manifest = read_bounded(manifest_path, MAX_JSON_BYTES, budget)
    require(raw_manifest == git(candidate, "show", "HEAD:docs/procurement-metadata-identity-contract.json"), "Manifest differs from candidate HEAD")
    manifest = decode_json(raw_manifest)
    require(manifest["base"] == BASE and manifest["baseTree"] == BASE_TREE and manifest["expectedTotalCases"] == 171,
            "Wrong immutable source baseline")
    require(set(manifest["profiles"]) == set(TESTS), "Wrong source profile roster")
    require_retired_source_custody(manifest)
    require(git(baseline, "rev-parse", "HEAD").decode().strip() == BASE
            and git(baseline, "rev-parse", "HEAD^{tree}").decode().strip() == BASE_TREE, "Wrong baseline head/tree")
    require(not git(baseline, "diff", "--name-only") and not git(baseline, "diff", "--cached", "--name-only"),
            "Tracked baseline source changed")
    require(not (baseline / METADATA_IDENTITY).exists(), "Candidate native metadata helper leaked into immutable baseline")
    for path, binding in ((FIXTURE, manifest["publicFixture"]), (TEST_PROJECT, manifest["joinTestProject"]), (API_PROJECT, manifest["buildProject"])):
        candidate_binding = (manifest["candidateJoinTestProject"] if path == TEST_PROJECT
                             else manifest["candidateBuildProject"] if path == API_PROJECT else binding)
        require(binding["path"] == candidate_binding["path"] == path
                and blob(candidate, path) == candidate_binding["gitBlob"], "Frozen candidate fixture/build input differs")
        baseline_raw = read_bounded(baseline / path, MAX_SOURCE_BYTES, budget)
        require(baseline_raw == git(baseline, "show", BASE + ":" + path)
                and blob(baseline, path) == binding["gitBlob"], "Immutable baseline fixture/build input differs")
        if path == FIXTURE:
            require(read_bounded(candidate / path, MAX_SOURCE_BYTES, budget) == baseline_raw,
                    "Public fixture differs across phases")
    require(not git(candidate, "diff", "--name-only") and not git(candidate, "diff", "--cached", "--name-only"), "Tracked candidate changed")
    directories = ("Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Application",
                   "Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Domain")
    require(not git(candidate, "ls-files", "--others", "--exclude-standard", "--", *directories,
                    "Legacy.Maliev.ProcurementService.Tests"), "Untracked compiled inputs forbidden")
    runtime = manifest["runtimePostimages"]
    allowed = {PROGRAM, API_PROJECT, CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY, SUPPLIER, SOURCE_FORMATTER, SOURCE_MODELS} | set(SUPPLIER_QUERY_RUNTIME)
    require(set(runtime) == allowed, "Wrong exact runtime input roster")
    require(set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--", *directories).decode().splitlines()) == allowed,
            "Unexpected production source/build drift")
    require_runtime_postimages(candidate, manifest)
    for path in ("scripts/observe-supplier-address-providers.py", "scripts/supplier_address_owned_processes.py",
                 "scripts/observe-file-metadata-providers.py", "scripts/verify-file-metadata-binding-results.py",
                 "scripts/verify-supplier-address-causal-results.py"):
        require(blob(candidate, path) == git(baseline, "rev-parse", BASE + ":" + path).decode().strip(),
                "Accepted causal/ownership implementation changed")
    require_script_bindings(candidate, manifest)
    for dependency, expected in {
        "Legacy.Maliev.ServiceDefaults": "ecb05cbbd68717e415f69df2ac488c1d323b1da3",
        "Legacy.Maliev.CompatibilityContracts": "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7",
    }.items():
        require(git(candidate / ".dependencies" / dependency, "rev-parse", "HEAD").decode().strip() == expected,
                "Wrong immutable public dependency")
    compiled_tests = set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--",
                             "Legacy.Maliev.ProcurementService.Tests").decode().splitlines())
    old_harness = manifest["candidateOnly108Harness"]
    require(old_harness["path"] == "Legacy.Maliev.ProcurementService.Tests/Integration/PurchaseOrderFileMetadataBindingTests.cs"
            and blob(candidate, old_harness["path"]) == old_harness["gitBlob"],
            "Reviewed108 native-oracle successor differs")
    boundary = manifest["candidateBoundaryHarness"]
    require(boundary["path"] == "Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs"
            and blob(candidate, boundary["path"]) == boundary["gitBlob"],
            "Reviewed three-Fact OpenAPI boundary successor differs")
    require(blob(baseline, boundary["path"])
            == git(baseline, "rev-parse", BASE + ":" + boundary["path"]).decode().strip(),
            "Original OpenAPI baseline must remain unchanged")
    allowed_tests = set(TESTS.values()) | {old_harness["path"], boundary["path"], TEST_PROJECT}
    source_harnesses = manifest["candidateSourceBodyHarnesses"]
    require(set(source_harnesses) == {"Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataOriginalModels.cs","Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataSourceOracle.cs","Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataSourceProtocolTests.cs","Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSourceBodyAdmissionTests.cs",
            "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierScalarStringTests.cs"},
            "Wrong source-body compiled harness roster")
    for path, record in source_harnesses.items():
        require(blob(candidate, path) == git_blob_record(record), "Source-body compiled harness differs")
    retained_scalar = manifest["previousSourceBodySupplierScalarHarness"]
    require(retained_scalar == {"path": "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierScalarStringTests.cs", "gitBlob": "1d9b4bb47360e4ba9b8f2864a03f63a2533b29a5"}
            and blob(baseline, retained_scalar["path"]) == retained_scalar["gitBlob"],
            "Retained scalar lexical baseline must remain unchanged")
    allowed_tests.update(source_harnesses)
    allowed_tests.update(require_header_harness_bindings(candidate, manifest))
    auth = manifest.get("authEnrollmentTestBinding")
    if auth is not None:
        require(isinstance(auth, dict) and set(auth) == {"path", "gitBlob"}
                and auth["path"] == "Legacy.Maliev.ProcurementService.Tests/Workflows/WorkflowContractTests.cs"
                and blob(candidate, auth["path"]) == git_blob_record({"gitBlob": auth["gitBlob"]}),
                "Wrong separately reviewed Auth workflow-test successor")
        allowed_tests.add(auth["path"])
    require(manifest["supplierOmittedSizeHarness"] == {"path": SUPPLIER_QUERY_TEST, "gitBlob": SUPPLIER_QUERY_TEST_BLOB}
            and blob(candidate, SUPPLIER_QUERY_TEST) == SUPPLIER_QUERY_TEST_BLOB,
            "Exact Supplier omitted-size compiled successor differs")
    allowed_tests.add(SUPPLIER_QUERY_TEST)
    require(compiled_tests == allowed_tests, "Unexpected compiled test drift")
    require(blob(baseline, old_harness["path"])
            == git(baseline, "rev-parse", BASE + ":" + old_harness["path"]).decode().strip(),
            "Original108 baseline must remain unchanged")
    admissions = require_admissions(candidate / "metadata-identity-results", verify_only)
    harnesses = {}
    for family, path in TESTS.items():
        profile = manifest["profiles"][family]
        require(profile["testPath"] == path and blob(candidate, path) == profile["testBlob"], "Original focused harness drift")
        raw = read_bounded(candidate / path, MAX_SOURCE_BYTES, budget)
        target = baseline / path
        if not verify_only:
            require(not target.exists(), "Baseline harness already exists before overlay")
            target.write_bytes(raw)
        require(read_bounded(target, MAX_SOURCE_BYTES, budget) == raw, "Baseline/candidate harness differs")
        harnesses[path] = {"gitBlob": profile["testBlob"], "sha256": hashlib.sha256(raw).hexdigest()}
    require(set(git(baseline, "ls-files", "--others", "--exclude-standard").decode().splitlines()) == set(TESTS.values()),
            "Unexpected baseline overlay")
    proof = {"schemaVersion": 1, "base": BASE, "baselineTree": BASE_TREE,
             "candidateCommit": git(candidate, "rev-parse", "HEAD").decode().strip(),
             "runtimePostimages": runtime, "harnesses": harnesses, "manifestSha256": hashlib.sha256(raw_manifest).hexdigest(),
             "verifiedAfterExecution": verify_only, "admissions": admissions, "owningRun": os.environ.get("GITHUB_RUN_ID"),
             "owningAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "wholeSourceModelParity": False}
    output = candidate / "metadata-identity-results"
    output.mkdir(exist_ok=True)
    if verify_only:
        proof["phases"] = [require_phase(output, phase, family, budget)
                           for phase in ("baseline", "candidate") for family in TESTS]
        spec = importlib.util.spec_from_file_location("metadata_identity_actual_results",
            candidate / "scripts/verify-metadata-identity-results.py")
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        for phase, code in (("baseline", 1), ("candidate", 0)):
            directory = output / (phase + "-metadata")
            actual = verifier.verify(directory, manifest, phase, "metadata", code,
                                     output / "baseline-metadata" if phase == "candidate" else None,
                                     record_proof=False)
            require(decode_json(read_bounded(directory / "metadata-identity-proof.json", MAX_JSON_BYTES, budget)) == actual,
                    "Final raw strict result proof changed after qualification")
    path = output / ("source-binding-after.json" if verify_only else "source-binding-before.json")
    if path.exists():
        require(decode_json(read_bounded(path, MAX_JSON_BYTES, budget)) == proof, "Preserved source proof changed")
    else:
        path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    prepare(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--verify-only" in sys.argv[3:])
