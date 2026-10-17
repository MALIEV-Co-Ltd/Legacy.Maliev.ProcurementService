"""Bind exact header199 source/actual phase proofs; no original binary or deployment claim."""
import datetime
import fnmatch
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

BASE = "44c79ed24c142883563e037bbb5be724ea87322a"
BASE_TREE = "869dab0b2a715def4a9c5613346d698a2943838e"
HEADER = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs"
SUPPLIER = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
METADATA_SEAM = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
NEW_METADATA_AUDIT = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredAuditDateTests.cs"
NEW_AUDIT = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredAuditTests.cs"
REPOSITORY = "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"
MIGRATION_TEST = "Legacy.Maliev.ProcurementService.Tests/Data/ProcurementPostgresMigrationTests.cs"
TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementHeaderIgnoredFieldsTests.cs"
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
TEST_PROJECT = "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"
OLD135 = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPurchaseOrderHeaderBindingTests.cs"
OPENAPI = "Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs"
FILE_HARNESS = "Legacy.Maliev.ProcurementService.Tests/Integration/PurchaseOrderFileMetadataBindingTests.cs"
COUNTRY_TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressCountryIdBindingTests.cs"
AUTH_TEST = "Legacy.Maliev.ProcurementService.Tests/Workflows/WorkflowContractTests.cs"
PROJECTS = tuple("Legacy.Maliev.ProcurementService." + part for part in ("Api", "Application", "Data", "Domain"))
PATTERNS = ("directory.build.*", "directory.packages.*", "global.json", "nuget.config", "*.slnx")
SCRIPT_PATHS = {
    "scripts/prepare-header-ignored-fields-baseline.py",
    "scripts/verify-header-ignored-fields-results.py",
    "scripts/observe-header-ignored-fields-providers.py",
    "scripts/test_header_ignored_fields_results.py",
    "scripts/require-metadata-identity-admission.py",
    ".github/workflows/procurement-header-ignored-fields.yml",
}
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TRX_BYTES = 16 * 1024 * 1024
MAX_PHASE_BYTES = 20 * 1024 * 1024
MAX_OPERATION_BYTES = 96 * 1024 * 1024


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
    proof_raw = read_bounded(directory / "header-ignored-fields-proof.json", MAX_JSON_BYTES, local)
    receipt_raw = read_bounded(directory / "provider-observation.json", MAX_JSON_BYTES, local)
    proof, receipt = decode_json(proof_raw), decode_json(receipt_raw)
    wanted = (59, 140, 1) if phase == "baseline" else (199, 0, 0)
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
            observed = decode_json(read_bounded(output / (phase + "-header") / "provider-observation.json",
                                               MAX_JSON_BYTES, [MAX_JSON_BYTES]))
            started = datetime.datetime.fromisoformat(observed["startedAtUtc"])
            require(started.tzinfo is not None and stamps[index] <= started,
                    "Test process started before its resource admission")
    return receipts


def tracked_inputs(root):
    selected = {}
    for record in git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8", errors="strict")
        if path in (FIXTURE, TEST_PROJECT) or any(path.startswith(project + "/") for project in PROJECTS) or (
            "/" not in path and any(fnmatch.fnmatchcase(path.lower(), pattern) for pattern in PATTERNS)
        ):
            selected[path] = metadata.decode("ascii", errors="strict")
    require(len(selected) == 72, "Exact reviewed72 runtime/build/public fixture inputs required")
    return selected


def prepare(baseline, manifest_path, verify_only=False):
    candidate = pathlib.Path(__file__).resolve().parents[1]
    budget = [MAX_OPERATION_BYTES]
    raw_manifest = read_bounded(manifest_path, MAX_JSON_BYTES, budget)
    require(raw_manifest == git(candidate, "show", "HEAD:docs/procurement-header-ignored-fields-contract.json"),
            "Manifest differs from candidate HEAD")
    manifest = decode_json(raw_manifest)
    require(manifest["base"] == BASE and manifest["baseTree"] == BASE_TREE
            and manifest["expectedTotalCases"] == 199 and set(manifest["profiles"]) == {"header"},
            "Wrong exact199 source baseline")
    require(git(baseline, "rev-parse", "HEAD").decode().strip() == BASE
            and git(baseline, "rev-parse", "HEAD^{tree}").decode().strip() == BASE_TREE,
            "Wrong immutable baseline head/tree")
    for root in (candidate, baseline):
        require(not git(root, "diff", "--name-only") and not git(root, "diff", "--cached", "--name-only"),
                "Tracked source changed")
    require(manifest.get("runtimeBindingFormat") == "git-blob-record-v1"
            and set(manifest["runtimePostimages"]) == {HEADER, REPOSITORY, SUPPLIER, METADATA_SEAM},
            "Only reviewed header, POST repository, and Supplier audit converter may change runtime")
    require(tracked_inputs(baseline) == manifest["baseInputs"]
            and tracked_inputs(candidate) == manifest["reviewedInputs"], "Frozen72 input inventory differs")
    differences = {path for path in manifest["baseInputs"]
                   if manifest["baseInputs"][path] != manifest["reviewedInputs"].get(path)}
    require(differences == {HEADER, REPOSITORY, SUPPLIER, METADATA_SEAM} and set(manifest["baseInputs"]) == set(manifest["reviewedInputs"]),
            "Exactly four reviewed runtime inputs may change")
    postimage = git_blob_record(manifest["runtimePostimages"][HEADER])
    require(blob(candidate, HEADER) == postimage
            and manifest["reviewedInputs"][HEADER] == "100644 blob " + postimage
            and manifest["baseInputs"][HEADER] == "100644 blob 8d6d8eb2c232a76bae57d6419a69da37b687b36d",
            "Header source postimage/preimage differs")
    repository_postimage = git_blob_record(manifest["runtimePostimages"][REPOSITORY])
    require(blob(candidate, REPOSITORY) == repository_postimage
            and manifest["reviewedInputs"][REPOSITORY] == "100644 blob " + repository_postimage
            and manifest["baseInputs"][REPOSITORY] == "100644 blob e3e6d902b10d7b985f12bb5d852982313cb13884",
            "POST repository source pre/postimage differs")
    metadata_postimage = git_blob_record(manifest["runtimePostimages"][METADATA_SEAM])
    require(blob(candidate, METADATA_SEAM) == metadata_postimage
            and manifest["reviewedInputs"][METADATA_SEAM] == "100644 blob " + metadata_postimage
            and manifest["baseInputs"][METADATA_SEAM] == "100644 blob be119d54a90a0772444b9f61f97be53a779610ba",
            "Metadata audit seam source postimage/preimage differs")
    for path in manifest["reviewedInputs"]:
        metadata = manifest["reviewedInputs"][path]
        require(re.fullmatch(r"100644 blob [0-9a-f]{40}", metadata) is not None
                and blob(candidate, path) == metadata.split()[-1], "Compiled input changed after checkout")
    for key, path in (("publicFixture", FIXTURE), ("joinTestProject", TEST_PROJECT)):
        binding = manifest[key]
        require(binding["path"] == path and blob(candidate, path) == binding["gitBlob"]
                and read_bounded(candidate / path, MAX_SOURCE_BYTES, budget)
                == read_bounded(baseline / path, MAX_SOURCE_BYTES, budget)
                == git(baseline, "show", BASE + ":" + path), "Frozen public fixture/build source differs")
    require(set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--", *PROJECTS).decode().splitlines()) == {HEADER, REPOSITORY, SUPPLIER, METADATA_SEAM},
            "Unexpected production source/build drift")
    require(not git(candidate, "ls-files", "--others", "--exclude-standard", "--", *PROJECTS,
                    "Legacy.Maliev.ProcurementService.Tests"), "Untracked compiled inputs forbidden")
    compiled = manifest["compiledTestPostimages"]
    require(set(compiled) == {TEST, OLD135, OPENAPI, AUTH_TEST, MIGRATION_TEST, NEW_AUDIT, NEW_METADATA_AUDIT, FILE_HARNESS, COUNTRY_TEST}, "Wrong closed compiled test roster")
    for path, record in compiled.items():
        require(blob(candidate, path) == git_blob_record(record), "Reviewed compiled test source differs")
    expected_changes = {TEST}
    for path in (OLD135, OPENAPI, AUTH_TEST, MIGRATION_TEST, NEW_AUDIT, NEW_METADATA_AUDIT, FILE_HARNESS, COUNTRY_TEST):
        if path in (NEW_AUDIT, NEW_METADATA_AUDIT, COUNTRY_TEST) or git(baseline, "rev-parse", BASE + ":" + path).decode().strip() != git_blob_record(compiled[path]):
            expected_changes.add(path)
    require(set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--",
                    "Legacy.Maliev.ProcurementService.Tests").decode().splitlines()) == expected_changes,
            "Unexpected compiled test drift")
    for path in ("scripts/supplier_address_owned_processes.py", "scripts/observe-metadata-identity-providers.py",
                 "scripts/require-metadata-identity-admission.py"):
        require(blob(candidate, path) == git(baseline, "rev-parse", BASE + ":" + path).decode().strip(),
                "Accepted owned resource/admission implementation changed")
    require_script_bindings(candidate, manifest)
    for dependency, expected in {
        "Legacy.Maliev.ServiceDefaults": "ecb05cbbd68717e415f69df2ac488c1d323b1da3",
        "Legacy.Maliev.CompatibilityContracts": "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7",
    }.items():
        require(git(candidate / ".dependencies" / dependency, "rev-parse", "HEAD").decode().strip() == expected,
                "Wrong immutable public dependency")
    profile = manifest["profiles"]["header"]
    require(profile["testPath"] == TEST and profile["testBlob"] == git_blob_record(compiled[TEST]),
            "Wrong original199 harness source")
    raw = read_bounded(candidate / TEST, MAX_SOURCE_BYTES, budget)
    target = baseline / TEST
    if not verify_only:
        require(not target.exists(), "Baseline harness exists before overlay")
        target.write_bytes(raw)
    require(read_bounded(target, MAX_SOURCE_BYTES, budget) == raw, "Actual baseline/candidate harness differs")
    require(set(git(baseline, "ls-files", "--others", "--exclude-standard").decode().splitlines()) == {TEST},
            "Only the new199 harness may overlay baseline")
    output = candidate / "header-ignored-fields-results"
    admissions = require_admissions(output, verify_only)
    proof = {"schemaVersion": 1, "base": BASE, "baselineTree": BASE_TREE,
             "candidateCommit": git(candidate, "rev-parse", "HEAD").decode().strip(),
             "runtimePostimages": manifest["runtimePostimages"], "harnessSha256": hashlib.sha256(raw).hexdigest(),
             "manifestSha256": hashlib.sha256(raw_manifest).hexdigest(), "onlyOverlay": TEST,
             "reviewedRuntimeBuildFixtureInputs": 72, "verifiedAfterExecution": verify_only,
             "admissions": admissions, "owningRun": os.environ.get("GITHUB_RUN_ID"),
             "owningAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "wholeSourceModelParity": False}
    output.mkdir(exist_ok=True)
    if verify_only:
        proof["phases"] = [require_phase(output, phase, "header", budget) for phase in ("baseline", "candidate")]
        spec = importlib.util.spec_from_file_location("header_ignored_fields_actual_results",
            candidate / "scripts/verify-header-ignored-fields-results.py")
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        for phase, code in (("baseline", 1), ("candidate", 0)):
            directory = output / (phase + "-header")
            actual = verifier.verify(directory, manifest, phase, "header", code,
                                     output / "baseline-header" if phase == "candidate" else None,
                                     record_proof=False)
            require(decode_json(read_bounded(directory / "header-ignored-fields-proof.json", MAX_JSON_BYTES, budget)) == actual,
                    "Final raw strict result proof changed after qualification")
    target_proof = output / ("source-binding-after.json" if verify_only else "source-binding-before.json")
    if target_proof.exists():
        require(decode_json(read_bounded(target_proof, MAX_JSON_BYTES, budget)) == proof,
                "Preserved source proof cannot be overwritten")
    else:
        target_proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    prepare(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--verify-only" in sys.argv[3:])
