"""Require exact producers, unchanged runtime/fixture inputs, and individual joined passes."""
import collections
import fnmatch
import hashlib
import json
import re
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/ProcurementAuthProgram.Tests/public-graph-fixture-owner-correlation.json"
HISTORICAL_PATH = "tools/ProcurementAuthProgram.Tests/public-graph.json"
HISTORICAL_SHA256 = "205063c79697948343ba659b13757b68ef4814d1b62861484a1dd90c0b8e7d41"
PREVIOUS_ACCEPTED_PATH = "tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json"
PREVIOUS_ACCEPTED_SHA256 = "d4aab5b24027fb666b8571c67450c59cd6b188970b34818fa308b34e215edd1a"
PROJECTS = tuple("Legacy.Maliev.ProcurementService." + part for part in ("Api", "Application", "Data", "Domain"))
FIXTURE = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs"
JOURNAL = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs"
JOURNAL_CONTROLS = "Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs"
FIXTURE_INPUTS = ('Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs')
PATTERNS = ("directory.build.*", "directory.packages.*", "global.json", "nuget.config", "*.slnx")


def tracked_inputs(repository):
    raw = subprocess.check_output(["git", "-C", str(repository), "ls-tree", "-r", "-z", "HEAD"])
    selected = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if path in FIXTURE_INPUTS or any(path.startswith(project + "/") for project in PROJECTS) or (
            "/" not in path and any(fnmatch.fnmatchcase(path.lower(), pattern) for pattern in PATTERNS)
        ):
            selected[path] = metadata.decode("ascii")
    return selected


def require_equal(current, reviewed):
    if current != reviewed or any(path not in reviewed for path in FIXTURE_INPUTS) or any(
        not any(path.startswith(project + "/") for path in reviewed) for project in PROJECTS
    ):
        raise ValueError("Runtime/build/public fixture drift requires a separately reviewed graph")


def require_source_change(reviewed, manifest):
    change = manifest["intentionalSourceChanges"]
    changes = change["changedInputs"]
    if not changes or len(reviewed) != change["inputCount"]:
        raise ValueError("Missing reviewed changes or runtime input count drift")
    for path, binding in changes.items():
        if path not in reviewed or reviewed[path] != binding["reviewedMetadata"]:
            raise ValueError("Intentional source changes do not match frozen metadata")
    unchanged = {name: metadata for name, metadata in reviewed.items() if name not in changes}
    digest = hashlib.sha256(json.dumps(unchanged, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if len(unchanged) != change["unchangedInputCount"] or digest != change["unchangedInputSha256"]:
        raise ValueError("Unrelated runtime/build/public fixture drift outside reviewed source string changes")


# This source-only draft intentionally cannot admit inputs/results before reviewed producer binding.
REVIEWED_CORRELATION_PRODUCER = "89aafbae9b6e0b42811ccf5112e084e276125bbe"
PREVIOUS_JOURNAL_GRAPH_PATH = 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-journal.json'
PREVIOUS_JOURNAL_GRAPH_SHA256 = 'b93372915b0a1a9b84426576baaec1c443437fdb2bc10804df5d93b83ca169ec'
FROZEN_OWNER_INPUT_METADATA = {'Directory.Build.props': '100644 blob b47c8d23651f11ea8366bb63f4520fb8de6c6df3', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs': '100644 blob 1bad18d6797295124d84083ba7f5e93276124c1e', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementPermissions.cs': '100644 blob 58a5a184edc50559048dd4b0329b80b5a6a57b5f', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementWorkloadExchangeGuard.cs': '100644 blob 2cbafd5644b7653a1eb323788be8f95bd98337ad', 'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs': '100644 blob 5382d06a862ff843bbb01539ddd8822070e86757', 'Legacy.Maliev.ProcurementService.Api/Controllers/OrderItemsController.cs': '100644 blob d5e94258bed07bff6c4c915ab4cb1e34fa368902', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs': '100644 blob 91b6bf11646f89f5c6736e7f54af964e044ae6ed', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrdersController.cs': '100644 blob 19530897851dcd97dbf52ee71d297f0b4cd0517c', 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs': '100644 blob 63dfa7c375090e0a1d3dd191f7430b1519c8bdea', 'Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs': '100644 blob f7549641da035088c553d07e42202c73ea881512', 'Legacy.Maliev.ProcurementService.Api/Dockerfile': '100644 blob b2c525d395006937f2faf1dbbe0ffa53b669e6d0', 'Legacy.Maliev.ProcurementService.Api/DurableChildCreateEndpoint.cs': '100644 blob 84b6da4468a7a22ae10d81aed8b29f6dab15dfaf', 'Legacy.Maliev.ProcurementService.Api/DurableCreateEndpoint.cs': '100644 blob 4a723a638129fbdb99a17758a06a8cd5c3f026ac', 'Legacy.Maliev.ProcurementService.Api/IdempotentCreates.cs': '100644 blob c8a0e7f92a10b833cd5a5254b0253f7537b67074', 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': '100644 blob 0fefb94217cd594e097c2e7aaee24da28b7c8c56', 'Legacy.Maliev.ProcurementService.Api/Program.cs': '100644 blob 19d17888cd77004b42f290a3c0daad454dfd4b5e', 'Legacy.Maliev.ProcurementService.Api/Properties/launchSettings.json': '100644 blob 5b49ab6aa8f800b7ed4a376abb9ccf0942625251', 'Legacy.Maliev.ProcurementService.Api/appsettings.Development.json': '100644 blob 0c208ae9181e5e5717e47ec1bd59368aebc6066e', 'Legacy.Maliev.ProcurementService.Api/appsettings.json': '100644 blob b057873ee272efdfc5311a0179a6214f4e1768b7', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementChildCreates.cs': '100644 blob b3cda03315eb9e70d9264a5a50fbdbfeef6c3705', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementCreates.cs': '100644 blob b91e35948db367bb5279029e5838a0e87617041c', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs': '100644 blob 90c2628be1aceef0178533add09fdea7efa4c42a', 'Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj': '100644 blob 8f5ac62cbd3b2f8cf8370a899a575e25d4a07dab', 'Legacy.Maliev.ProcurementService.Application/Models/DurableCreateModels.cs': '100644 blob 6fce05a93ea834e1fc661e0938456e92b908a003', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': '100644 blob f20b6e2ac31e8a4e91567fca14cf6af449e3b3f0', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementTransactionUncertainException.cs': '100644 blob 6486a812e5e78ae8e8be9bcf54ee8683989e0615', 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs': '100644 blob cdbfc2e43f4d8575006df249836145cf7ecb50d6', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs': '100644 blob a450e196d981d66aef98b6a5970e6f1f53bcef67', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs': '100644 blob 25834e7c9705786777a707734b914fbf99987cfc', 'Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs': '100644 blob 9b17fd46fce25162e30854210a1f945a1f9d6f48', 'Legacy.Maliev.ProcurementService.Data/ChildReceiptRecords.cs': '100644 blob 8974e76d5c72762828a0d32624a09faaafe8dda4', 'Legacy.Maliev.ProcurementService.Data/CreateReceiptRecord.cs': '100644 blob 7df3a2a661854d928fb4ac6363596546419ffeb3', 'Legacy.Maliev.ProcurementService.Data/DistributedProcurementCache.cs': '100644 blob cd88f078148dadf470850b383874f2453c3ab146', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementChildCreates.cs': '100644 blob 0fe45073973624adcf21d6abcef8a23ced035f97', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementCreates.cs': '100644 blob d8e7d7f4182fc613a399990acf9109f0ca7a9e3a', 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': '100644 blob c152c047af1ddb1bcedccf08b25d6a03320d34f3', 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs': '100644 blob 2e68e9f383160dfe6082f7a23b859bfbf5b2d325', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.Designer.cs': '100644 blob ff647d92152d6acaa1b5d54c2381711263a6e38a', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.cs': '100644 blob f27917f143b0cbdf2809881b96c2ccce3b4dccb8', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.Designer.cs': '100644 blob 2e9588ac6e0a9da4feaa4fb59a683f785560c713', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs': '100644 blob 86049cb052f1390dad51c9800f301d2af411a87f', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.Designer.cs': '100644 blob 9ab941b4fbbc26b1bf4277328792cc594936e7ca', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.cs': '100644 blob 8b1f910f078b8a4d13f15c6903a9825e0198bbbf', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs': '100644 blob 143e1ae02a1fd1100eb2d75dce9b8124188e4cd4', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs': '100644 blob 1663bacce0bf61de8db5688a82e48354c24ba658', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.Designer.cs': '100644 blob 71271d8755686ea6609b0d794484ec8ae29e41eb', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.cs': '100644 blob 2ba84b62673cd157fd53807eeb21bb9c59375422', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs': '100644 blob b3477b7823f63b37bed92959f7100e3cd287baf9', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.Designer.cs': '100644 blob 84c0f1841ecd125e52dbdd8fff6d560cf26baab7', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.cs': '100644 blob 2d36ff6600a6c973baf717fe07c61e72a3cad80e', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.Designer.cs': '100644 blob 7edb0df2fe539c86629d0296e95ae428506d2a90', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs': '100644 blob f6c70ffcb468140850659ff2dee07290d5b891b4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.Designer.cs': '100644 blob 022a0c30e60b669e22b310ba6f589244f4d004fa', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.cs': '100644 blob 653202333c192a7c96844f639858f9e362524d77', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs': '100644 blob a36060169d6812f83f1fe764faddc0c0eeee2fea', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs': '100644 blob 8c82219082c3a6f2bb629a65d72d8a459b07b5d4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs': '100644 blob e77cced2826569ba96cb46d659e0fb90be8ceb0e', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContextFactories.cs': '100644 blob 0eadcec30749cdccde9c4a8eae39e5f9c9a0ec80', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs': '100644 blob 1a8487f24a647a186258d487b84e1cc08fa7d83b', 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': '100644 blob e3e6d902b10d7b985f12bb5d852982313cb13884', 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs': '100644 blob c182f47f50e92fd3225c08d14bcb505e49d73ad5', 'Legacy.Maliev.ProcurementService.Data/ReceiptReadiness.cs': '100644 blob 7e252a2a88928f12d421b10fe7cf831146268b9d', 'Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj': '100644 blob 51addf44ecf979d69d9d77527d402f14c06a4fa5', 'Legacy.Maliev.ProcurementService.Domain/ProcurementEntities.cs': '100644 blob 141a05708c3374afe8ad9471698a892addbf2531', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs': '100644 blob 6f9ab7b766565ceba5522e53df39cd4008c38a7e', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs': '100644 blob 43ea0949935b0486d8932c927cad90ab8a1ccb3d', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': '100644 blob 006d1f0f51d09a0dfac35d40f75baa5d1dff44bd', 'Legacy.Maliev.ProcurementService.slnx': '100644 blob 48c1f4ac9b6141df5596bcdc99eb0b22b4a1213e', 'nuget.config': '100644 blob 765346e5343d46ac83654843869dc06b65b2bdc4', 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': '100644 blob 82894df31a17ed37a3ff453fbfa27818c34eecc2', 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': '100644 blob 3d6a4b8d2979c3daad819cf0e764fcdd26dd71f6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': '100644 blob 1fb3433cb2bb99b38367da14e4c49e8f1cc004a6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': '100644 blob c5c7911f988340e12921156496893ecacc0f1489', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': '100644 blob b86a3e160e2b982e8a76cac99a68558399aea64d', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs': '100644 blob 67346c8762a43d2008a18ae47064e0353a9997bc', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs': '100644 blob 42fed43b45e6aeb62f924f493ed72aa91b8dd18a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs': '100644 blob 697aafc6da82909931e9e958fc2997cee7f48291', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs': '100644 blob 561e3c5eeb9ddf8cabc997b14a5aa4f36af2fcfe', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': '100644 blob e180274800334e331a8f0ae4fed73bc10b84328a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs': '100644 blob 59843a80df60331827a6dda29e48db18fd49b2a8'}
PRODUCTION_BUILD_SHA256 = '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443'
FROZEN_OWNER_SOURCE_CHANGE = {'previousProcurement': '24099f8e88ea14eebfa9a995dcd5f7569dad3dbf', 'acceptedBase': 'f84d493ea3cbfd9667d1a2e2a31fabebfc0bba93', 'reviewedProcurement': None, 'inputCount': 80, 'changedInputs': {'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': {'previousMetadata': '100644 blob 73933ffa40816460f8770b2cf72183fd499d648d', 'reviewedMetadata': '100644 blob 82894df31a17ed37a3ff453fbfa27818c34eecc2', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': {'previousMetadata': '100644 blob c7817e2409b49f32423230199bda79a5e79609cd', 'reviewedMetadata': '100644 blob 3d6a4b8d2979c3daad819cf0e764fcdd26dd71f6', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': {'previousMetadata': '100644 blob f9b4e2b337d1e2dce1f94a9c68c18f22ab444456', 'reviewedMetadata': '100644 blob 1fb3433cb2bb99b38367da14e4c49e8f1cc004a6', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': {'previousMetadata': '100644 blob b482c7ed604319943b17c20ced3c63784423108e', 'reviewedMetadata': '100644 blob c5c7911f988340e12921156496893ecacc0f1489', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': {'previousMetadata': '100644 blob 33371e000bcffa8c5e047f893bf0cd11d96b525b', 'reviewedMetadata': '100644 blob b86a3e160e2b982e8a76cac99a68558399aea64d', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 67346c8762a43d2008a18ae47064e0353a9997bc', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 42fed43b45e6aeb62f924f493ed72aa91b8dd18a', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 697aafc6da82909931e9e958fc2997cee7f48291', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 561e3c5eeb9ddf8cabc997b14a5aa4f36af2fcfe', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': {'previousMetadata': '100644 blob 012c4ba6c7ce26a3ad222ea6f0f9d7029af1f6ed', 'reviewedMetadata': '100644 blob 006d1f0f51d09a0dfac35d40f75baa5d1dff44bd', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': {'previousMetadata': '100644 blob a5ecdb83358ec34bc0230feaf008446405f4daca', 'reviewedMetadata': '100644 blob e180274800334e331a8f0ae4fed73bc10b84328a', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}}, 'unchangedInputCount': 69, 'unchangedInputSha256': 'e09dedf99a42dee3fb8c8550709b1084553902f735b06ce8f02de7e482e99923', 'productionBuildInputCount': 66, 'productionBuildInputSha256': '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443', 'scope': 'Exact explicit owner correlation80 source graph; no production/runtime behavior change', 'nativeAcceptance': 'Fresh actualAuth15 required; new16 compile input is not execution proof', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}
FROZEN_OWNER_GRAPH_KEYS = ('graphId', 'references', 'defaultsAdoption', 'expectedCases', 'expectedMethods', 'fixtureEnrollment', 'productionEnrollmentProven', 'productionIamBridgeProven', 'wholeInitialSourceParityClosed', 'previousMasterQuerySourceChange', 'nullableSortProducerAdvance', 'literalObjectNameProducerAdvance', 'previousIntentionalSourceChange', 'intentionalSourceChanges', 'previousStringIntentionalSourceChanges', 'previousLiteralIntentionalSourceChanges', 'historicalGraph', 'previousSupplierPrimitiveIntentionalSourceChanges', 'credentialCorrection', 'compilerCorrection', 'runtimeCorrection', 'previousAcceptedGraph', 'latestAcceptedSupplierGraph', 'previousBucketIntentionalSourceChanges', 'latestAcceptedBucketGraph', 'previousPurchaseOrderAddressIntentionalSourceChanges', 'latestAcceptedPurchaseOrderAddressGraph', 'previousFixtureIntentionalSourceChanges', 'previousReviewedFixtureGraph', 'previousReviewedStartupDiagnosticGraph', 'previousReviewedStartupJournalGraph', 'ownerCorrelationSourceBinding')


def require_owner_graph(manifest):
    producer = REVIEWED_CORRELATION_PRODUCER
    if not isinstance(producer, str) or re.fullmatch(r"[0-9a-f]{40}", producer) is None:
        raise ValueError("Owner correlation producer is unbound; draft source cannot admit native validation")
    if set(manifest) != set(FROZEN_OWNER_GRAPH_KEYS):
        raise ValueError("Owner graph has unknown or missing fields")
    require_historical_graph(manifest)
    predecessor_bytes = (ROOT / PREVIOUS_JOURNAL_GRAPH_PATH).read_bytes()
    custody = manifest["previousReviewedStartupJournalGraph"]
    if custody != {"path":PREVIOUS_JOURNAL_GRAPH_PATH, "sha256":PREVIOUS_JOURNAL_GRAPH_SHA256,
                   "procurement":"24099f8e88ea14eebfa9a995dcd5f7569dad3dbf", "inputCount":69,
                   "qualification":"Immutable predecessor source custody; native scope stays separate"} or hashlib.sha256(predecessor_bytes).hexdigest() != PREVIOUS_JOURNAL_GRAPH_SHA256:
        raise ValueError("Previous journal69 graph custody changed")
    previous = json.loads(predecessor_bytes)
    require_historical_graph(previous)
    if set(manifest) != set(FROZEN_OWNER_GRAPH_KEYS):
        raise ValueError("Owner graph has unknown or missing fields")
    for field,value in previous.items():
        if field not in ("graphId", "references", "intentionalSourceChanges") and manifest[field] != value:
            raise ValueError("Preserved predecessor graph field changed: " + field)
    external = lambda value: [entry for entry in value["references"] if entry["repository"] != "Legacy.Maliev.ProcurementService"]
    if external(manifest) != external(previous) or manifest["expectedCases"] != previous["expectedCases"] or manifest["expectedMethods"] != previous["expectedMethods"]:
        raise ValueError("External producers or actual Auth15 identities changed")
    entries = [entry for entry in manifest["references"] if entry["repository"] == "Legacy.Maliev.ProcurementService"]
    binding = manifest["ownerCorrelationSourceBinding"]
    if len(entries) != 1 or entries[0]["commit"] != producer or binding != {
            "reviewedProducer":producer, "inputMetadata":FROZEN_OWNER_INPUT_METADATA, "releaseAllowed":True}:
        raise ValueError("Reviewed owner80 immutable source binding differs")
    change = manifest["intentionalSourceChanges"]
    expected_change = dict(FROZEN_OWNER_SOURCE_CHANGE)
    expected_change["reviewedProcurement"] = producer
    if change != expected_change:
        raise ValueError("Exact reviewed owner source-change metadata differs")
    if change["reviewedProcurement"] != producer or change["inputCount"] != 80 or change["productionBuildInputCount"] != 66 or change["productionBuildInputSha256"] != PRODUCTION_BUILD_SHA256:
        raise ValueError("Exact80/66 reviewed source custody differs")
    require_source_change(FROZEN_OWNER_INPUT_METADATA, manifest)
    production = {path:metadata for path,metadata in FROZEN_OWNER_INPUT_METADATA.items() if path not in FIXTURE_INPUTS}
    if len(production) != 66 or hashlib.sha256(json.dumps(production,sort_keys=True,separators=(",",":")).encode()).hexdigest() != PRODUCTION_BUILD_SHA256:
        raise ValueError("Unchanged66 production/build inputs differ")


def require_owner_inputs(current, reviewed, manifest):
    require_equal(current, reviewed)
    if current != FROZEN_OWNER_INPUT_METADATA or len(current) != 80:
        raise ValueError("Owner80 selected source inputs drift")
    require_source_change(reviewed, manifest)


def inputs(root, manifest):
    require_owner_graph(manifest)
    for entry in manifest["references"]:
        repository, expected = entry["repository"], entry["commit"]
        actual = subprocess.check_output(["git", "-C", str(root / repository), "rev-parse", "HEAD"], text=True).strip()
        if actual != expected:
            raise ValueError("Producer checkout does not equal the immutable graph pin: " + repository)
    reviewed = tracked_inputs(root / "Legacy.Maliev.ProcurementService")
    require_equal(tracked_inputs(ROOT), reviewed)
    require_owner_inputs(tracked_inputs(ROOT), reviewed, manifest)
    print(json.dumps({"graphId": manifest["graphId"], "references": manifest["references"], "identicalRuntimeBuildFixtureInputs": len(reviewed)}))


def require_historical_graph(manifest):
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
    scalar_custody = manifest["latestAcceptedPurchaseOrderAddressGraph"]
    scalar_path = "tools/ProcurementAuthProgram.Tests/public-graph-purchase-order-address.json"
    scalar_sha = "9ac11ba51211e1c17cde9385bb31f8e952eef302892233c867c8e04c64bb5c0a"
    scalar_bytes = (ROOT / scalar_path).read_bytes()
    if scalar_custody != {"path": scalar_path, "sha256": scalar_sha, "procurement": "430d2cabbdaa712e3536a119abe88f9167021358", "inputCount": 67} or hashlib.sha256(scalar_bytes).hexdigest() != scalar_sha:
        raise ValueError("Accepted purchase-order address67 graph custody must remain exact")
    fixture_custody = manifest["previousReviewedFixtureGraph"]
    fixture_path = "tools/ProcurementAuthProgram.Tests/public-graph-fixture-containment.json"
    fixture_sha = "1dfc57fa5a10f49b16f224e6f04b0a1355c75996ae9f624fdaec5e27913b6d64"
    fixture_bytes = (ROOT / fixture_path).read_bytes()
    if fixture_custody != {"path": fixture_path, "sha256": fixture_sha, "procurement": "1e520e795ec534ac9512ccf1bdb272a34e5140e9", "inputCount": 67, "qualification": "Reviewed draft source only; native fixture containment not accepted"} or hashlib.sha256(fixture_bytes).hexdigest() != fixture_sha:
        raise ValueError("Reviewed fixture67 graph custody must remain exact without runtime qualification")
    startup_path = "tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-diagnostics.json"
    startup_sha = "f8c54c39bf4e81c0674001e47993faa0f0ab2d8e281d2170cc508ba6e50c1a24"
    if (manifest["previousReviewedStartupDiagnosticGraph"] != {"path": startup_path, "sha256": startup_sha,
            "procurement": "61746f2fe03fd71eb3f208bfbf861eef800b9599", "inputCount": 67,
            "qualification": "Reviewed source custody only; predecessor native claims remain separate"}
            or hashlib.sha256((ROOT / startup_path).read_bytes()).hexdigest() != startup_sha):
        raise ValueError("Previous startup67 graph custody must remain immutable")
    external = lambda graph: {entry["repository"]: entry["commit"] for entry in graph["references"] if entry["repository"] != "Legacy.Maliev.ProcurementService"}
    if external(manifest) != external(historical) or manifest["expectedCases"] != historical["expectedCases"] or manifest["expectedMethods"] != historical["expectedMethods"]:
        raise ValueError("External producer pins and actual Auth execution identities must remain unchanged")
    if any(manifest[field] is not False for field in ("productionEnrollmentProven", "productionIamBridgeProven", "wholeInitialSourceParityClosed")):
        raise ValueError("Source custody does not qualify production authority or whole-source closure")


def results(root, manifest):
    require_owner_graph(manifest)
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
