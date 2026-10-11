"""Overlay only the frozen test harness onto the immutable production baseline."""
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


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args],timeout=15)


def prepare(baseline, manifest_path, verify_only=False):
    candidate=pathlib.Path(__file__).resolve().parents[1]
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest['expectedCases']==33 and len(manifest['cases'])==33,'Wrong frozen roster')
    require(git(baseline,'rev-parse','HEAD').decode().strip()==BASE,'Baseline is not immutable accepted main')
    require(not git(baseline,'diff','--name-only') and not git(baseline,'diff','--cached','--name-only'),'Existing baseline files changed')
    require((candidate/FIXTURE).read_bytes()==(baseline/FIXTURE).read_bytes()==git(baseline,'show',BASE+':'+FIXTURE),'Public provider fixture differs between phases')
    require(not (baseline/CONVERTER).exists(),'Candidate converter leaked into baseline')
    harness=(candidate/TEST).read_bytes()
    require(hashlib.sha256(harness).hexdigest()==HARNESS_SHA256,'Frozen harness source changed')
    model=(baseline/MODEL).read_bytes()
    require(model==git(baseline,'show',BASE+':'+MODEL),'Baseline production model changed')
    require(b'public sealed record UpsertSupplierAddressRequest(string? Building, string? Address1, string? Address2, string? City, string? State, string? PostalCode, int CountryId);' in model,'Baseline lost original address string binding')
    require(model.count(b'JsonConverter(typeof(SupplierScalarStringJsonConverter))')==8,'Accepted master field bindings regressed')
    target=baseline/TEST
    if not verify_only:
        require(not target.exists(),'Baseline harness already exists before overlay')
        target.write_bytes(harness)
    require(target.read_bytes()==harness,'Baseline and candidate harness differ')
    require(set(git(baseline,'ls-files','--others','--exclude-standard').decode().splitlines())=={TEST},'Unexpected baseline overlay files')
    output=candidate/'address-causal-results'
    output.mkdir(exist_ok=True)
    proof={'base':BASE,'baselineTree':git(baseline,'rev-parse','HEAD^{tree}').decode().strip(),
           'candidateCommit':git(candidate,'rev-parse','HEAD').decode().strip(),'harnessSha256':HARNESS_SHA256,
           'fixtureSha256':hashlib.sha256((candidate/FIXTURE).read_bytes()).hexdigest(),'onlyOverlay':TEST,
           'verifiedAfterExecution':verify_only,'baselineNativeExecutionProven':False}
    (output/('source-binding-after.json' if verify_only else 'source-binding-before.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),'--verify-only' in sys.argv[3:])
