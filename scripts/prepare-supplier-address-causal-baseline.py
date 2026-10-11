"""Overlay the frozen case harness and reviewed fixture onto an immutable production baseline."""
import hashlib
import json
import pathlib
import subprocess
import sys


BASE = '95d5b212b64f56ba3dfdfe4abe05b18110fc248d'
TEST = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs'
FIXTURE = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs'
MODEL = 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs'
CONVERTER = 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs'
HARNESS_SHA256 = '8fe88e09de5368db558831e763da9c1ffaba44d4d58cf392afd2c505ade99a17'
FIXTURE_PRODUCER = '61746f2fe03fd71eb3f208bfbf861eef800b9599'
FIXTURE_BLOB = 'e2c124b0f734b8bcfad370e776817ebfbdaf53e0'
FIXTURE_SHA256 = '67d1149ca88ae88d392588309b347a8fe9503dd5c37ff4998c31261752e49538'
ORIGINAL_FIXTURE_SHA256 = '7a5823479455c30cac411b51cfed4ebbe247f2648e7d087167392e62be8efb20'


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args],timeout=15)


def require_fixture_binding(candidate, baseline, original, verify_only):
    require(hashlib.sha256(original).hexdigest() == ORIGINAL_FIXTURE_SHA256, 'Original baseline fixture custody changed')
    require(hashlib.sha256(candidate).hexdigest() == FIXTURE_SHA256, 'Candidate differs from independently reviewed immutable fixture')
    require(baseline == (candidate if verify_only else original), 'Baseline fixture differs from exact reviewed phase overlay')


def require_harness_binding(harness):
    require(hashlib.sha256(harness).hexdigest()==HARNESS_SHA256,'Frozen harness source changed')


def require_previous_overlay(overlay, previous_bytes):
    previous_path = 'docs/procurement-supplier-address-fixture-overlay.json'
    previous_sha = '73ac06dfd1af3523cfe13a03ad88bee20c8b9a46c9bb051dba02002fa5ff87d2'
    require(overlay['previousReviewedFixtureOverlay']=={'path':previous_path,'sha256':previous_sha,'producer':'1e520e795ec534ac9512ccf1bdb272a34e5140e9','fixtureSha256':'b5a69c9200bad7dd57e577125e9c75935ce3540af87f1b3410b3f5f9453c33e6','qualification':'Reviewed source only; not native fixture acceptance'} and hashlib.sha256(previous_bytes).hexdigest()==previous_sha,'Prior reviewed fixture overlay custody changed')


def prepare(baseline, manifest_path, verify_only=False):
    candidate=pathlib.Path(__file__).resolve().parents[1]
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest['expectedCases']==33 and len(manifest['cases'])==33,'Wrong frozen roster')
    require(git(baseline,'rev-parse','HEAD').decode().strip()==BASE,'Baseline is not immutable accepted main')
    expected_tracked = {FIXTURE} if verify_only else set()
    require(set(git(baseline,'diff','--name-only').decode().splitlines()) == expected_tracked and not git(baseline,'diff','--cached','--name-only'),'Baseline production or unreviewed tracked files changed')
    overlay = json.loads((candidate/'docs/procurement-supplier-address-fixture-startup-overlay.json').read_text(encoding='utf-8'))
    require(overlay['reviewedFixtureProducer']==FIXTURE_PRODUCER and overlay['reviewedFixtureBlob']==FIXTURE_BLOB and overlay['reviewedFixtureSha256']==FIXTURE_SHA256 and overlay['originalBaseline']==BASE and overlay['originalBaselineFixtureSha256']==ORIGINAL_FIXTURE_SHA256 and overlay['fixturePath']==FIXTURE,'Fixture overlay manifest custody differs')
    require_previous_overlay(overlay, (candidate/'docs/procurement-supplier-address-fixture-overlay.json').read_bytes())
    original_fixture=git(baseline,'show',BASE+':'+FIXTURE)
    reviewed_fixture=(candidate/FIXTURE).read_bytes()
    require_fixture_binding(reviewed_fixture,(baseline/FIXTURE).read_bytes(),original_fixture,verify_only)
    require(not (baseline/CONVERTER).exists(),'Candidate converter leaked into baseline')
    harness=(candidate/TEST).read_bytes()
    require_harness_binding(harness)
    model=(baseline/MODEL).read_bytes()
    require(model==git(baseline,'show',BASE+':'+MODEL),'Baseline production model changed')
    require(b'public sealed record UpsertSupplierAddressRequest(string? Building, string? Address1, string? Address2, string? City, string? State, string? PostalCode, int CountryId);' in model,'Baseline lost original address string binding')
    require(model.count(b'JsonConverter(typeof(SupplierScalarStringJsonConverter))')==8,'Accepted master field bindings regressed')
    target=baseline/TEST
    if not verify_only:
        require(not target.exists(),'Baseline harness already exists before overlay')
        target.write_bytes(harness)
        (baseline/FIXTURE).write_bytes(reviewed_fixture)
    require(target.read_bytes()==harness,'Baseline and candidate harness differ')
    require((baseline/FIXTURE).read_bytes()==reviewed_fixture,'Baseline and candidate public fixtures differ after overlay')
    require(set(git(baseline,'diff','--name-only').decode().splitlines())=={FIXTURE},'Only reviewed test fixture tracked overlay is allowed')
    require(set(git(baseline,'ls-files','--others','--exclude-standard').decode().splitlines())=={TEST},'Unexpected baseline overlay files')
    output=candidate/'address-causal-results'
    output.mkdir(exist_ok=True)
    proof={'base':BASE,'baselineTree':git(baseline,'rev-parse','HEAD^{tree}').decode().strip(),
           'candidateCommit':git(candidate,'rev-parse','HEAD').decode().strip(),'harnessSha256':HARNESS_SHA256,
           'fixtureSha256':FIXTURE_SHA256,'onlyOverlay':TEST,'trackedTestFixtureOverlay':FIXTURE,
           'reviewedFixtureProducer':FIXTURE_PRODUCER,'reviewedFixtureBlob':FIXTURE_BLOB,
           'originalBaselineFixtureSha256':ORIGINAL_FIXTURE_SHA256,
           'verifiedAfterExecution':verify_only,'baselineNativeExecutionProven':False}
    (output/('source-binding-after.json' if verify_only else 'source-binding-before.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),'--verify-only' in sys.argv[3:])
