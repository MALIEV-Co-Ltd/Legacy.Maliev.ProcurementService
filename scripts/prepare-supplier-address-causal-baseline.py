"""Overlay the frozen case harness and reviewed fixture onto an immutable production baseline."""
import hashlib
import json
import pathlib
import re
import subprocess
import sys


BASE = '95d5b212b64f56ba3dfdfe4abe05b18110fc248d'
TEST = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs'
FIXTURE = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs'
MODEL = 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs'
CONVERTER = 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs'
HARNESS_SHA256 = '8fe88e09de5368db558831e763da9c1ffaba44d4d58cf392afd2c505ade99a17'
FIXTURE_PRODUCER = "5da322779bb7b32b1f858ab6cba2bfafe0a4d9fd"
FIXTURE_BLOB = 'a4fda2edca34c7e8f918d8c43edd72438ed66f05'
FIXTURE_SHA256 = 'f6d8f287e32cf2837f8b25eb470e4a6ba2f66e27940af9f429a1e04f15ce439b'
HELPER = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs'
HELPER_BLOB = '6f9ab7b766565ceba5522e53df39cd4008c38a7e'
HELPER_SHA256 = '4642aba334a59cd3dfb0cc636c903d4ea3a9cae6a1e68951b387dde30faf7253'
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


def require_helper_binding(candidate, baseline, verify_only):
    require(hashlib.sha256(candidate).hexdigest()==HELPER_SHA256, 'Reviewed helper bytes changed')
    require(baseline == candidate if verify_only else baseline is None, 'Baseline helper differs from exact reviewed phase')


def require_previous_startup_overlay(overlay, previous_bytes):
    require(overlay['previousReviewedStartupOverlay']=={
        'path':'docs/procurement-supplier-address-fixture-startup-overlay.json',
        'sha256':'b70ce7d077a58961fa08b7035adc0687133629fae7466f88df15e60c08af72b5',
        'producer':'61746f2fe03fd71eb3f208bfbf861eef800b9599',
        'qualification':'Preserve original617 diagnostic overlay as immutable predecessor'} and
        hashlib.sha256(previous_bytes).hexdigest()=='b70ce7d077a58961fa08b7035adc0687133629fae7466f88df15e60c08af72b5',
        'Prior startup overlay custody changed')


def require_previous_overlay(overlay, previous_bytes):
    previous_path = 'docs/procurement-supplier-address-fixture-overlay.json'
    previous_sha = '73ac06dfd1af3523cfe13a03ad88bee20c8b9a46c9bb051dba02002fa5ff87d2'
    require(overlay['previousReviewedFixtureOverlay']=={'path':previous_path,'sha256':previous_sha,'producer':'1e520e795ec534ac9512ccf1bdb272a34e5140e9','fixtureSha256':'b5a69c9200bad7dd57e577125e9c75935ce3540af87f1b3410b3f5f9453c33e6','qualification':'Reviewed source only; not native fixture acceptance'} and hashlib.sha256(previous_bytes).hexdigest()==previous_sha,'Prior reviewed fixture overlay custody changed')


OWNER_HELPER = 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs'
OWNER_HELPER_BLOB = 'f710b2a0f435eb2b6f648ee9cf2c15a5a0d57058'
OWNER_HELPER_SHA256 = 'a2062e5e3ddd8d4541ceafae86287d600b68cca421236652e70a9d62d6609a28'
PREVIOUS_JOURNAL_OVERLAY = 'docs/procurement-supplier-address-fixture-journal-overlay.json'
PREVIOUS_JOURNAL_OVERLAY_SHA256 = '56e8b42df2a8a64c241dfd214f086f79ed7c71b5c2d8e18e71dbf491b857396a'


def require_release_producer():
    require(isinstance(FIXTURE_PRODUCER,str) and re.fullmatch(r"[0-9a-f]{40}", FIXTURE_PRODUCER) is not None,
            'Owner correlation producer is unbound; draft cannot prepare a native baseline')


def require_owner_helper_binding(candidate, baseline, verify_only):
    require(hashlib.sha256(candidate).hexdigest()==OWNER_HELPER_SHA256, 'Reviewed owner helper bytes changed')
    require(baseline == candidate if verify_only else baseline is None, 'Baseline owner helper differs from reviewed phase')


def require_previous_journal_overlay(overlay, previous_bytes):
    require(overlay['previousReviewedJournalOverlay']=={'path':PREVIOUS_JOURNAL_OVERLAY,
        'sha256':PREVIOUS_JOURNAL_OVERLAY_SHA256,'producer':'24099f8e88ea14eebfa9a995dcd5f7569dad3dbf',
        'qualification':'Immutable predecessor journal overlay; not new correlation acceptance'} and
        hashlib.sha256(previous_bytes).hexdigest()==PREVIOUS_JOURNAL_OVERLAY_SHA256,
        'Previous journal overlay custody changed')
    previous=json.loads(previous_bytes)
    require_previous_overlay(previous, (pathlib.Path(__file__).resolve().parents[1]/'docs/procurement-supplier-address-fixture-overlay.json').read_bytes())
    require_previous_startup_overlay(previous, (pathlib.Path(__file__).resolve().parents[1]/'docs/procurement-supplier-address-fixture-startup-overlay.json').read_bytes())


def prepare(baseline, manifest_path, verify_only=False):
    require_release_producer()
    candidate=pathlib.Path(__file__).resolve().parents[1]
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    require(manifest['expectedCases']==33 and len(manifest['cases'])==33,'Wrong frozen roster')
    require(git(baseline,'rev-parse','HEAD').decode().strip()==BASE,'Baseline is not immutable accepted main')
    expected_tracked = {FIXTURE} if verify_only else set()
    require(set(git(baseline,'diff','--name-only').decode().splitlines()) == expected_tracked and not git(baseline,'diff','--cached','--name-only'),'Baseline production or unreviewed tracked files changed')
    expected_untracked = {TEST,HELPER,OWNER_HELPER} if verify_only else set()
    require(set(git(baseline,'ls-files','--others','--exclude-standard').decode().splitlines()) == expected_untracked,
            'Baseline contains unexpected untracked inputs before phase verification')
    overlay = json.loads((candidate/'docs/procurement-supplier-address-fixture-owner-correlation-overlay.json').read_text(encoding='utf-8'))
    require(overlay['reviewedFixtureProducer']==FIXTURE_PRODUCER and overlay['reviewedFixtureBlob']==FIXTURE_BLOB and overlay['reviewedFixtureSha256']==FIXTURE_SHA256 and overlay['originalBaseline']==BASE and overlay['originalBaselineFixtureSha256']==ORIGINAL_FIXTURE_SHA256 and overlay['fixturePath']==FIXTURE,'Fixture overlay manifest custody differs')
    require(overlay['releaseAllowed'] is True, 'Owner correlation overlay remains draft-only')
    require_previous_journal_overlay(overlay, (candidate/PREVIOUS_JOURNAL_OVERLAY).read_bytes())
    require_previous_overlay(overlay, (candidate/'docs/procurement-supplier-address-fixture-overlay.json').read_bytes())
    require_previous_startup_overlay(overlay, (candidate/'docs/procurement-supplier-address-fixture-startup-overlay.json').read_bytes())
    require(overlay['helperOverlay']=={'path':HELPER,'producer':'24099f8e88ea14eebfa9a995dcd5f7569dad3dbf','gitBlob':HELPER_BLOB,'sha256':HELPER_SHA256,
        'classification':'Additional test-only runtime journal/publication dependency; must be absent in untouched95d5 baseline; identical in both phases'}, 'Helper overlay metadata differs')
    require(overlay['ownerCorrelationHelper']=={'path':OWNER_HELPER,'producer':FIXTURE_PRODUCER,
        'gitBlob':OWNER_HELPER_BLOB,'sha256':OWNER_HELPER_SHA256,
        'classification':'Additional test-only owner correlation helper; absent in untouched95 baseline; identical in both phases'}, 'Owner helper overlay metadata differs')
    producer=candidate/'.dependencies/ProcurementFixtureProducer'
    require(git(producer,'rev-parse','HEAD').decode().strip()==FIXTURE_PRODUCER,
            'Fixture producer checkout must have the exact immutable source HEAD')
    require(git(producer,'rev-parse','--is-shallow-repository').decode().strip()=='true',
            'Fixture producer checkout must retain bounded depth1 history')
    require(not git(producer,'diff','--name-only') and not git(producer,'diff','--cached','--name-only')
            and not git(producer,'ls-files','--others','--exclude-standard'), 'Fixture producer checkout changed')
    for path,blob in [(FIXTURE,FIXTURE_BLOB),(OWNER_HELPER,OWNER_HELPER_BLOB)]:
        require(git(producer,'rev-parse',FIXTURE_PRODUCER+':'+path).decode().strip()==blob,
                'Fixture producer object blob differs from exact reviewed binding')
        require(git(producer,'show',FIXTURE_PRODUCER+':'+path)==(candidate/path).read_bytes(),
                'Current input does not match immutable reviewed fixture producer')
    original_fixture=git(baseline,'show',BASE+':'+FIXTURE)
    reviewed_fixture=(candidate/FIXTURE).read_bytes()
    require_fixture_binding(reviewed_fixture,(baseline/FIXTURE).read_bytes(),original_fixture,verify_only)
    require(not git(baseline,'ls-tree',BASE,'--',HELPER), 'Helper already exists in immutable production baseline')
    reviewed_helper=(candidate/HELPER).read_bytes()
    require_helper_binding(reviewed_helper,(baseline/HELPER).read_bytes() if (baseline/HELPER).exists() else None,verify_only)
    require(not git(baseline,'ls-tree',BASE,'--',OWNER_HELPER),'Owner helper exists in untouched baseline')
    reviewed_owner_helper=(candidate/OWNER_HELPER).read_bytes()
    require_owner_helper_binding(reviewed_owner_helper,(baseline/OWNER_HELPER).read_bytes() if (baseline/OWNER_HELPER).exists() else None,verify_only)
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
        (baseline/HELPER).write_bytes(reviewed_helper)
        (baseline/OWNER_HELPER).write_bytes(reviewed_owner_helper)
    require(target.read_bytes()==harness,'Baseline and candidate harness differ')
    require((baseline/FIXTURE).read_bytes()==reviewed_fixture,'Baseline and candidate public fixtures differ after overlay')
    require((baseline/HELPER).read_bytes()==reviewed_helper,'Baseline and candidate journal helpers differ after overlay')
    require((baseline/OWNER_HELPER).read_bytes()==reviewed_owner_helper,'Baseline and candidate owner helpers differ after overlay')
    require(set(git(baseline,'diff','--name-only').decode().splitlines())=={FIXTURE},'Only reviewed test fixture tracked overlay is allowed')
    require(set(git(baseline,'ls-files','--others','--exclude-standard').decode().splitlines())=={TEST,HELPER,OWNER_HELPER},'Unexpected baseline overlay files')
    output=candidate/'address-causal-results'
    output.mkdir(exist_ok=True)
    proof={'base':BASE,'baselineTree':git(baseline,'rev-parse','HEAD^{tree}').decode().strip(),
           'candidateCommit':git(candidate,'rev-parse','HEAD').decode().strip(),'harnessSha256':HARNESS_SHA256,
           'fixtureSha256':FIXTURE_SHA256,'onlyOverlay':TEST,'trackedTestFixtureOverlay':FIXTURE,
           'reviewedFixtureProducer':FIXTURE_PRODUCER,'reviewedFixtureBlob':FIXTURE_BLOB,
           'producerCheckoutHead':git(producer,'rev-parse','HEAD').decode().strip(),
           'producerCheckoutTree':git(producer,'rev-parse','HEAD^{tree}').decode().strip(),
           'producerCheckoutShallow':True,
           'additionalTestOnlyHelper':HELPER,'helperSha256':HELPER_SHA256,'helperBlob':HELPER_BLOB,
           'ownerCorrelationHelper':OWNER_HELPER,'ownerHelperSha256':OWNER_HELPER_SHA256,'ownerHelperBlob':OWNER_HELPER_BLOB,
           'originalBaselineFixtureSha256':ORIGINAL_FIXTURE_SHA256,
           'verifiedAfterExecution':verify_only,'baselineNativeExecutionProven':False}
    (output/('source-binding-after.json' if verify_only else 'source-binding-before.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),'--verify-only' in sys.argv[3:])
