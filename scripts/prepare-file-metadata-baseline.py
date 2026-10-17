"""Bind only the new test harness to the immutable file-metadata baseline."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

BASE = "0c0f622d07a03c7bd5dcbb731d3b8afa07b1fbc4"
PROGRAM = "Legacy.Maliev.ProcurementService.Api/Program.cs"
CONVERTER = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs"
METADATA_IDENTITY = "Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs"
HEADER = "Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs"
REPOSITORY = "Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs"
API_PROJECT = "Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj"
SUPPLIER_CONVERTER = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
TEST = "Legacy.Maliev.ProcurementService.Tests/Integration/PurchaseOrderFileMetadataBindingTests.cs"


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    # Keep even source-metadata stdout off the heap until its actual read is capped.
    with tempfile.TemporaryFile() as output:
        subprocess.run(["git", "-C", str(root), *args], stdout=output, check=True, timeout=15)
        output.seek(0)
        raw = output.read(4 * 1024 * 1024 + 1)
    require(len(raw) <= 4 * 1024 * 1024, "Git source metadata exceeds the bounded reader")
    return raw


def blob(root, path):
    return git(root, "hash-object", path).decode().strip()



MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TRX_BYTES = 16 * 1024 * 1024
MAX_PHASE_BYTES = 20 * 1024 * 1024
MAX_PREPARE_BYTES = 64 * 1024 * 1024


def read_bounded(path, maximum, budget):
    limit = min(maximum, budget[0])
    require(limit >= 0, "Negative proof read budget")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "Proof/source evidence exceeds the bounded reader")
    budget[0] -= len(raw)
    return raw


def decode_json(raw):
    return json.loads(raw.decode("utf-8-sig", errors="strict"))


def phase_reports(directory):
    reports = []
    for path in directory.rglob("*.trx"):
        require(not reports, "Multiple phase TRX files")
        reports.append(path)
    return reports


def git_blob_record(value):
    require(isinstance(value, dict) and set(value) == {"gitBlob"}
            and isinstance(value["gitBlob"], str)
            and re.fullmatch(r"[0-9a-f]{40}", value["gitBlob"]) is not None,
            "Require one explicit public Git blob provenance record")
    return value["gitBlob"]


def require_runtime_roster(value):
    require(isinstance(value, dict) and set(value) == {PROGRAM, CONVERTER, API_PROJECT, SUPPLIER_CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY},
            "Runtime postimage roster must equal the seven reviewed current inputs")
    for record in value.values():
        git_blob_record(record)


def runtime_bindings(manifest):
    require(manifest.get("runtimeBindingFormat") == "git-blob-record-v1",
            "Require the reviewed Git blob provenance format")
    value = manifest["implementationRuntime"]
    require_runtime_roster(value)
    return {path: git_blob_record(record) for path, record in value.items()}


def require_runtime_postimages(candidate, manifest):
    for path, expected in runtime_bindings(manifest).items():
        require(blob(candidate, path) == expected, "Candidate runtime postimage differs: " + path)


def require_phase_evidence(output, phase, budget=None):
    directory = output / phase
    budget = [MAX_PHASE_BYTES] if budget is None else budget
    proof_raw = read_bounded(directory / "file-metadata-binding-proof.json", MAX_JSON_BYTES, budget)
    receipt_raw = read_bounded(directory / "provider-observation.json", MAX_JSON_BYTES, budget)
    proof, receipt = decode_json(proof_raw), decode_json(receipt_raw)
    expected = (6, 10, 1) if phase == "baseline" else (108, 0, 0)
    require(type(receipt.get("exitCode")) is int
            and (proof.get("passed"), proof.get("failed"), receipt.get("exitCode")) == expected
            and proof.get("phase") == receipt.get("phase") == phase and proof.get("skipped") == 0,
            "Wrong actual phase result/exit")
    require(receipt.get("owningRun") == os.environ.get("GITHUB_RUN_ID")
            and receipt.get("owningAttempt") == os.environ.get("GITHUB_RUN_ATTEMPT"), "Wrong phase receipt custody")
    require(receipt.get("processExited") is True and receipt.get("normalFixtureDisposalProven") is True
            and receipt.get("resourcesAbsent") is True and receipt.get("uncertainResourcesPreserved") is False
            and receipt.get("errors") == [], "Phase disposal is unproven")
    cleanup = receipt.get("processSessionCleanup") or {}
    require(cleanup.get("verified") is True and cleanup.get("forcedCleanup") is False
            and cleanup.get("handlesClosed") is True and cleanup.get("launcherExited") is True
            and cleanup.get("remainingSessionMembers") == [] and cleanup.get("cleanupErrors") == [],
            "Phase process cleanup is unproven")
    disposal = receipt.get("disposalObservation") or {}
    require(disposal.get("settled") is True and disposal.get("errors") == [], "Provider disposal did not settle")
    polls = disposal.get("polls") or []
    require(bool(polls) and polls[-1].get("containerInventoryAvailable") is True
            and polls[-1].get("volumeInventoryAvailable") is True
            and polls[-1].get("remainingContainerIds") == [] and polls[-1].get("remainingVolumeNames") == [],
            "Terminal resource inventories are incomplete")
    reports = phase_reports(directory)
    require(len(reports) == 1, "One phase TRX required")
    trx_raw = read_bounded(reports[0], MAX_TRX_BYTES, budget)
    require(hashlib.sha256(trx_raw).hexdigest() == proof.get("trxSha256") == receipt.get("rawTrxSha256"),
            "Phase receipt/raw TRX hash differs")
    return {"phase": phase, "proofSha256": hashlib.sha256(proof_raw).hexdigest(),
            "receiptSha256": hashlib.sha256(receipt_raw).hexdigest(),
            "trxSha256": proof["trxSha256"], "normalDisposal": True}


def prepare(baseline, manifest_path, verify_only=False):
    candidate = pathlib.Path(__file__).resolve().parents[1]
    budget = [MAX_PREPARE_BYTES]
    manifest_raw = read_bounded(manifest_path, MAX_JSON_BYTES, budget)
    manifest = decode_json(manifest_raw)
    require(manifest["base"] == BASE and manifest["expectedCandidateCases"] == 108
            and manifest["harness"]["path"] == TEST, "Wrong source manifest/base")
    require(git(baseline, "rev-parse", "HEAD").decode().strip() == BASE, "Baseline head is not immutable accepted main")
    require(not git(baseline, "diff", "--name-only") and not git(baseline, "diff", "--cached", "--name-only"), "Tracked baseline source changed")
    require(git(baseline, "rev-parse", "HEAD^{tree}").decode().strip() == "003c85339032b5055fc464434f05ed72d26014c1", "Baseline tree differs")
    require(not (baseline / CONVERTER).exists(), "Candidate converter leaked into baseline")
    require(read_bounded(baseline / PROGRAM, MAX_SOURCE_BYTES, budget) == git(baseline, "show", BASE + ":" + PROGRAM), "Baseline Program changed")
    fixture_raw = read_bounded(candidate / FIXTURE, MAX_SOURCE_BYTES, budget)
    require(fixture_raw == read_bounded(baseline / FIXTURE, MAX_SOURCE_BYTES, budget)
            == git(baseline, "show", BASE + ":" + FIXTURE), "Public fixture changed between phases")
    require(not git(candidate, "diff", "--name-only") and not git(candidate, "diff", "--cached", "--name-only"),
            "Tracked candidate source changed during qualification")
    require(not git(candidate, "ls-files", "--others", "--exclude-standard", "--",
                    "Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Application",
                    "Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Domain",
                    "Legacy.Maliev.ProcurementService.Tests"), "Untracked compiled source inputs are forbidden")
    expected_runtime = manifest["implementationRuntime"]
    require_runtime_roster(expected_runtime)
    changed = set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--",
                      "Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Application",
                      "Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Domain").decode().splitlines())
    require(changed == {PROGRAM, CONVERTER, API_PROJECT, SUPPLIER_CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY}, "Unexpected production source changes")
    require_runtime_postimages(candidate, manifest)
    for path in ("scripts/observe-supplier-address-providers.py", "scripts/supplier_address_owned_processes.py"):
        require(blob(candidate, path) == git(baseline, "rev-parse", BASE + ":" + path).decode().strip(),
                "Reviewed process/provider ownership implementation changed")
    require(blob(candidate, TEST) == manifest["harness"]["gitBlob"], "Reviewed harness postimage changed")
    harness = read_bounded(candidate / TEST, MAX_SOURCE_BYTES, budget)
    target = baseline / TEST
    if not verify_only:
        require(not target.exists(), "Baseline harness already exists before overlay")
        target.write_bytes(harness)
    require(read_bounded(target, MAX_SOURCE_BYTES, budget) == harness, "Baseline/candidate harness differs")
    require(set(git(baseline, "ls-files", "--others", "--exclude-standard").decode().splitlines()) == {TEST},
            "Unexpected baseline overlay")
    proof = {"schemaVersion": 1, "base": BASE,
             "baselineTree": git(baseline, "rev-parse", "HEAD^{tree}").decode().strip(),
             "candidateCommit": git(candidate, "rev-parse", "HEAD").decode().strip(),
             "harnessGitBlob": manifest["harness"]["gitBlob"],
             "harnessSha256": hashlib.sha256(harness).hexdigest(),
             "fixtureSha256": hashlib.sha256(fixture_raw).hexdigest(),
             "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
             "runtimePostimages": expected_runtime, "onlyOverlay": TEST, "verifiedAfterExecution": verify_only,
             "owningRun": os.environ.get("GITHUB_RUN_ID"), "owningAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
             "wholeSourceModelParity": False, "productionEnrollmentProven": False}
    output = candidate / "file-metadata-results"
    output.mkdir(exist_ok=True)
    if verify_only:
        proof["phases"] = [require_phase_evidence(output, phase, budget) for phase in ("baseline", "candidate")]
    path = output / ("source-binding-after.json" if verify_only else "source-binding-before.json")
    if path.exists():
        require(decode_json(read_bounded(path, MAX_JSON_BYTES, budget)) == proof, "Refuse to overwrite different source binding")
    else:
        path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    prepare(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--verify-only" in sys.argv[3:])
