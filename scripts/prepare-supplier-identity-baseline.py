"""Bind the original supplier identity harnesses to immutable e885 main."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

BASE = "e8850889cb81b5bdf5bac5fdd1c55f2ed08cae8d"
BASE_TREE = "e380830777da16ddd6834642b1df8a6761cf2f87"
PROGRAM = "Legacy.Maliev.ProcurementService.Api/Program.cs"
API_PROJECT = "Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj"
CONVERTER = "Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs"
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
TEST_PROJECT = "Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj"
TESTS = {
    "id": "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredIdTests.cs",
    "address": "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredAddressIdTests.cs",
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
    proof_raw = read_bounded(directory / "supplier-identity-proof.json", MAX_JSON_BYTES, local)
    receipt_raw = read_bounded(directory / "provider-observation.json", MAX_JSON_BYTES, local)
    proof, receipt = decode_json(proof_raw), decode_json(receipt_raw)
    wanted = ((26, 29, 1) if family == "id" else (30, 22, 1)) if phase == "baseline" else ((55, 0, 0) if family == "id" else (52, 0, 0))
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


def prepare(baseline, manifest_path, verify_only=False):
    candidate = pathlib.Path(__file__).resolve().parents[1]
    budget = [MAX_OPERATION_BYTES]
    raw_manifest = read_bounded(manifest_path, MAX_JSON_BYTES, budget)
    require(raw_manifest == git(candidate, "show", "HEAD:docs/procurement-supplier-identity-contract.json"), "Manifest differs from candidate HEAD")
    manifest = decode_json(raw_manifest)
    require(manifest["base"] == BASE and manifest["baseTree"] == BASE_TREE and manifest["expectedTotalCases"] == 107,
            "Wrong immutable source baseline")
    require(set(manifest["profiles"]) == set(TESTS), "Wrong source profile roster")
    require(git(baseline, "rev-parse", "HEAD").decode().strip() == BASE
            and git(baseline, "rev-parse", "HEAD^{tree}").decode().strip() == BASE_TREE, "Wrong baseline head/tree")
    require(not git(baseline, "diff", "--name-only") and not git(baseline, "diff", "--cached", "--name-only"),
            "Tracked baseline source changed")
    require(not (baseline / CONVERTER).exists(), "Candidate converter leaked into immutable baseline")
    for path, binding in ((FIXTURE, manifest["publicFixture"]), (TEST_PROJECT, manifest["joinTestProject"])):
        require(binding["path"] == path and blob(candidate, path) == binding["gitBlob"], "Frozen fixture/build input differs")
        require(read_bounded(candidate / path, MAX_SOURCE_BYTES, budget)
                == read_bounded(baseline / path, MAX_SOURCE_BYTES, budget)
                == git(baseline, "show", BASE + ":" + path), "Public fixture/build inputs differ across phases")
    require(not git(candidate, "diff", "--name-only") and not git(candidate, "diff", "--cached", "--name-only"), "Tracked candidate changed")
    directories = ("Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Application",
                   "Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Domain")
    require(not git(candidate, "ls-files", "--others", "--exclude-standard", "--", *directories,
                    "Legacy.Maliev.ProcurementService.Tests"), "Untracked compiled inputs forbidden")
    runtime = manifest["runtimePostimages"]
    allowed = {PROGRAM, API_PROJECT, CONVERTER}
    require(set(runtime) == allowed, "Wrong exact runtime input roster")
    require(set(git(candidate, "diff", "--name-only", BASE, "HEAD", "--", *directories).decode().splitlines()) == allowed,
            "Unexpected production source/build drift")
    for path, expected in runtime.items():
        require(blob(candidate, path) == expected, "Wrong reviewed runtime postimage: " + path)
    for path in ("scripts/observe-supplier-address-providers.py", "scripts/supplier_address_owned_processes.py",
                 "scripts/observe-file-metadata-providers.py", "scripts/verify-file-metadata-binding-results.py",
                 "scripts/verify-supplier-address-causal-results.py"):
        require(blob(candidate, path) == git(baseline, "rev-parse", BASE + ":" + path).decode().strip(),
                "Accepted causal/ownership implementation changed")
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
             "verifiedAfterExecution": verify_only, "owningRun": os.environ.get("GITHUB_RUN_ID"),
             "owningAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "wholeSourceModelParity": False}
    output = candidate / "supplier-identity-results"
    output.mkdir(exist_ok=True)
    if verify_only:
        proof["phases"] = [require_phase(output, phase, family, budget)
                           for phase in ("baseline", "candidate") for family in TESTS]
    path = output / ("source-binding-after.json" if verify_only else "source-binding-before.json")
    if path.exists():
        require(decode_json(read_bounded(path, MAX_JSON_BYTES, budget)) == proof, "Preserved source proof changed")
    else:
        path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    prepare(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--verify-only" in sys.argv[3:])
