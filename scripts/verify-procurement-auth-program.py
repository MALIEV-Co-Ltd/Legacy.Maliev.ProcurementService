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


def tracked_inputs(repository, revision='HEAD'):
    raw = subprocess.check_output(["git", "-C", str(repository), "ls-tree", "-r", "-z", revision], timeout=15)
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
REVIEWED_CORRELATION_PRODUCER = "4a117fb68cebffc9e0acae9000750e8e45ec62cc"
PREVIOUS_JOURNAL_GRAPH_PATH = 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-journal.json'
PREVIOUS_JOURNAL_GRAPH_SHA256 = 'b93372915b0a1a9b84426576baaec1c443437fdb2bc10804df5d93b83ca169ec'
FROZEN_OWNER_INPUT_METADATA = {'Directory.Build.props': '100644 blob b47c8d23651f11ea8366bb63f4520fb8de6c6df3', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs': '100644 blob 1bad18d6797295124d84083ba7f5e93276124c1e', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementPermissions.cs': '100644 blob 58a5a184edc50559048dd4b0329b80b5a6a57b5f', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementWorkloadExchangeGuard.cs': '100644 blob 2cbafd5644b7653a1eb323788be8f95bd98337ad', 'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs': '100644 blob 5382d06a862ff843bbb01539ddd8822070e86757', 'Legacy.Maliev.ProcurementService.Api/Controllers/OrderItemsController.cs': '100644 blob d5e94258bed07bff6c4c915ab4cb1e34fa368902', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs': '100644 blob 91b6bf11646f89f5c6736e7f54af964e044ae6ed', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrdersController.cs': '100644 blob 19530897851dcd97dbf52ee71d297f0b4cd0517c', 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs': '100644 blob 63dfa7c375090e0a1d3dd191f7430b1519c8bdea', 'Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs': '100644 blob f7549641da035088c553d07e42202c73ea881512', 'Legacy.Maliev.ProcurementService.Api/Dockerfile': '100644 blob b2c525d395006937f2faf1dbbe0ffa53b669e6d0', 'Legacy.Maliev.ProcurementService.Api/DurableChildCreateEndpoint.cs': '100644 blob 84b6da4468a7a22ae10d81aed8b29f6dab15dfaf', 'Legacy.Maliev.ProcurementService.Api/DurableCreateEndpoint.cs': '100644 blob 4a723a638129fbdb99a17758a06a8cd5c3f026ac', 'Legacy.Maliev.ProcurementService.Api/IdempotentCreates.cs': '100644 blob c8a0e7f92a10b833cd5a5254b0253f7537b67074', 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': '100644 blob 0fefb94217cd594e097c2e7aaee24da28b7c8c56', 'Legacy.Maliev.ProcurementService.Api/Program.cs': '100644 blob 19d17888cd77004b42f290a3c0daad454dfd4b5e', 'Legacy.Maliev.ProcurementService.Api/Properties/launchSettings.json': '100644 blob 5b49ab6aa8f800b7ed4a376abb9ccf0942625251', 'Legacy.Maliev.ProcurementService.Api/appsettings.Development.json': '100644 blob 0c208ae9181e5e5717e47ec1bd59368aebc6066e', 'Legacy.Maliev.ProcurementService.Api/appsettings.json': '100644 blob b057873ee272efdfc5311a0179a6214f4e1768b7', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementChildCreates.cs': '100644 blob b3cda03315eb9e70d9264a5a50fbdbfeef6c3705', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementCreates.cs': '100644 blob b91e35948db367bb5279029e5838a0e87617041c', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs': '100644 blob 90c2628be1aceef0178533add09fdea7efa4c42a', 'Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj': '100644 blob 8f5ac62cbd3b2f8cf8370a899a575e25d4a07dab', 'Legacy.Maliev.ProcurementService.Application/Models/DurableCreateModels.cs': '100644 blob 6fce05a93ea834e1fc661e0938456e92b908a003', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': '100644 blob f20b6e2ac31e8a4e91567fca14cf6af449e3b3f0', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementTransactionUncertainException.cs': '100644 blob 6486a812e5e78ae8e8be9bcf54ee8683989e0615', 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs': '100644 blob cdbfc2e43f4d8575006df249836145cf7ecb50d6', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs': '100644 blob a450e196d981d66aef98b6a5970e6f1f53bcef67', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs': '100644 blob 25834e7c9705786777a707734b914fbf99987cfc', 'Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs': '100644 blob 9b17fd46fce25162e30854210a1f945a1f9d6f48', 'Legacy.Maliev.ProcurementService.Data/ChildReceiptRecords.cs': '100644 blob 8974e76d5c72762828a0d32624a09faaafe8dda4', 'Legacy.Maliev.ProcurementService.Data/CreateReceiptRecord.cs': '100644 blob 7df3a2a661854d928fb4ac6363596546419ffeb3', 'Legacy.Maliev.ProcurementService.Data/DistributedProcurementCache.cs': '100644 blob cd88f078148dadf470850b383874f2453c3ab146', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementChildCreates.cs': '100644 blob 0fe45073973624adcf21d6abcef8a23ced035f97', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementCreates.cs': '100644 blob d8e7d7f4182fc613a399990acf9109f0ca7a9e3a', 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': '100644 blob c152c047af1ddb1bcedccf08b25d6a03320d34f3', 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs': '100644 blob 2e68e9f383160dfe6082f7a23b859bfbf5b2d325', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.Designer.cs': '100644 blob ff647d92152d6acaa1b5d54c2381711263a6e38a', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.cs': '100644 blob f27917f143b0cbdf2809881b96c2ccce3b4dccb8', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.Designer.cs': '100644 blob 2e9588ac6e0a9da4feaa4fb59a683f785560c713', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs': '100644 blob 86049cb052f1390dad51c9800f301d2af411a87f', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.Designer.cs': '100644 blob 9ab941b4fbbc26b1bf4277328792cc594936e7ca', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.cs': '100644 blob 8b1f910f078b8a4d13f15c6903a9825e0198bbbf', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs': '100644 blob 143e1ae02a1fd1100eb2d75dce9b8124188e4cd4', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs': '100644 blob 1663bacce0bf61de8db5688a82e48354c24ba658', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.Designer.cs': '100644 blob 71271d8755686ea6609b0d794484ec8ae29e41eb', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.cs': '100644 blob 2ba84b62673cd157fd53807eeb21bb9c59375422', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs': '100644 blob b3477b7823f63b37bed92959f7100e3cd287baf9', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.Designer.cs': '100644 blob 84c0f1841ecd125e52dbdd8fff6d560cf26baab7', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.cs': '100644 blob 2d36ff6600a6c973baf717fe07c61e72a3cad80e', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.Designer.cs': '100644 blob 7edb0df2fe539c86629d0296e95ae428506d2a90', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs': '100644 blob f6c70ffcb468140850659ff2dee07290d5b891b4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.Designer.cs': '100644 blob 022a0c30e60b669e22b310ba6f589244f4d004fa', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.cs': '100644 blob 653202333c192a7c96844f639858f9e362524d77', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs': '100644 blob a36060169d6812f83f1fe764faddc0c0eeee2fea', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs': '100644 blob 8c82219082c3a6f2bb629a65d72d8a459b07b5d4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs': '100644 blob e77cced2826569ba96cb46d659e0fb90be8ceb0e', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContextFactories.cs': '100644 blob 0eadcec30749cdccde9c4a8eae39e5f9c9a0ec80', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs': '100644 blob 1a8487f24a647a186258d487b84e1cc08fa7d83b', 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': '100644 blob e3e6d902b10d7b985f12bb5d852982313cb13884', 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs': '100644 blob c182f47f50e92fd3225c08d14bcb505e49d73ad5', 'Legacy.Maliev.ProcurementService.Data/ReceiptReadiness.cs': '100644 blob 7e252a2a88928f12d421b10fe7cf831146268b9d', 'Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj': '100644 blob 51addf44ecf979d69d9d77527d402f14c06a4fa5', 'Legacy.Maliev.ProcurementService.Domain/ProcurementEntities.cs': '100644 blob 141a05708c3374afe8ad9471698a892addbf2531', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs': '100644 blob 6f9ab7b766565ceba5522e53df39cd4008c38a7e', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs': '100644 blob 43ea0949935b0486d8932c927cad90ab8a1ccb3d', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': '100644 blob a4fda2edca34c7e8f918d8c43edd72438ed66f05', 'Legacy.Maliev.ProcurementService.slnx': '100644 blob 48c1f4ac9b6141df5596bcdc99eb0b22b4a1213e', 'nuget.config': '100644 blob 765346e5343d46ac83654843869dc06b65b2bdc4', 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': '100644 blob 82894df31a17ed37a3ff453fbfa27818c34eecc2', 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': '100644 blob 3d6a4b8d2979c3daad819cf0e764fcdd26dd71f6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': '100644 blob 1fb3433cb2bb99b38367da14e4c49e8f1cc004a6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': '100644 blob c5c7911f988340e12921156496893ecacc0f1489', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': '100644 blob 281a7f13123f16a96cacd2d9465d909c0c07bae0', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs': '100644 blob 67346c8762a43d2008a18ae47064e0353a9997bc', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs': '100644 blob f710b2a0f435eb2b6f648ee9cf2c15a5a0d57058', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs': '100644 blob 432386cd0e1557860431bef87345c66fbe9ef41a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs': '100644 blob 561e3c5eeb9ddf8cabc997b14a5aa4f36af2fcfe', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': '100644 blob e180274800334e331a8f0ae4fed73bc10b84328a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs': '100644 blob 2ec6c2d9b59bb8cf3b6035005489acba1589c4b2'}
PRODUCTION_BUILD_SHA256 = '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443'
FROZEN_OWNER_SOURCE_CHANGE = {'previousProcurement': '24099f8e88ea14eebfa9a995dcd5f7569dad3dbf', 'acceptedBase': 'f84d493ea3cbfd9667d1a2e2a31fabebfc0bba93', 'reviewedProcurement': '4a117fb68cebffc9e0acae9000750e8e45ec62cc', 'inputCount': 80, 'changedInputs': {'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': {'previousMetadata': '100644 blob 73933ffa40816460f8770b2cf72183fd499d648d', 'reviewedMetadata': '100644 blob 82894df31a17ed37a3ff453fbfa27818c34eecc2', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': {'previousMetadata': '100644 blob c7817e2409b49f32423230199bda79a5e79609cd', 'reviewedMetadata': '100644 blob 3d6a4b8d2979c3daad819cf0e764fcdd26dd71f6', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': {'previousMetadata': '100644 blob f9b4e2b337d1e2dce1f94a9c68c18f22ab444456', 'reviewedMetadata': '100644 blob 1fb3433cb2bb99b38367da14e4c49e8f1cc004a6', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': {'previousMetadata': '100644 blob b482c7ed604319943b17c20ced3c63784423108e', 'reviewedMetadata': '100644 blob c5c7911f988340e12921156496893ecacc0f1489', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': {'previousMetadata': '100644 blob 33371e000bcffa8c5e047f893bf0cd11d96b525b', 'reviewedMetadata': '100644 blob 281a7f13123f16a96cacd2d9465d909c0c07bae0', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 67346c8762a43d2008a18ae47064e0353a9997bc', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob f710b2a0f435eb2b6f648ee9cf2c15a5a0d57058', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 432386cd0e1557860431bef87345c66fbe9ef41a', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 561e3c5eeb9ddf8cabc997b14a5aa4f36af2fcfe', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': {'previousMetadata': '100644 blob 012c4ba6c7ce26a3ad222ea6f0f9d7029af1f6ed', 'reviewedMetadata': '100644 blob a4fda2edca34c7e8f918d8c43edd72438ed66f05', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': {'previousMetadata': '100644 blob a5ecdb83358ec34bc0230feaf008446405f4daca', 'reviewedMetadata': '100644 blob e180274800334e331a8f0ae4fed73bc10b84328a', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs': {'previousMetadata': '100644 blob 59843a80df60331827a6dda29e48db18fd49b2a8', 'reviewedMetadata': '100644 blob 2ec6c2d9b59bb8cf3b6035005489acba1589c4b2', 'classification': 'Test-only owner correlation source/consumer/compile dependency; not native execution proof'}}, 'unchangedInputCount': 68, 'unchangedInputSha256': '9ef3d5d9e7cfd3c4885425d332d41c860b982c3d6454a3f5caeb144b3c27655f', 'productionBuildInputCount': 66, 'productionBuildInputSha256': '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443', 'scope': 'Exact explicit owner correlation80 source graph; no production/runtime behavior change', 'nativeAcceptance': 'Fresh actualAuth15 required; new16 compile input is not execution proof', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}
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
        actual = subprocess.check_output(["git", "-C", str(root / repository), "rev-parse", "HEAD"], text=True, timeout=15).strip()
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


# Diagnostic dependency v2 is inactive until a genuine producer is reviewed.
DIAGNOSTIC_PRODUCER = None
DIAGNOSTIC_PATHS = FIXTURE_INPUTS + (
    'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableDiagnosticPolicy.cs',
    'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableDiagnosticPolicyTests.cs',
)
OWNER_PREDECESSOR_PATH = 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-owner-correlation-v1.json'
OWNER_PREDECESSOR_SHA256 = '5394705469105e1b020f4a7fe44247964605fe7c9e6cad51177c7667a1dd5b23'
FROZEN_DIAGNOSTIC_GRAPH = {'graphId': 'procurement-auth-diagnostic-dependencies-v2', 'references': [{'repository': 'Legacy.Maliev.AuthService', 'commit': 'b27fbef06a3aa58c1f4fc0e75d7c70b32be76266'}, {'repository': 'Legacy.Maliev.ServiceDefaults', 'commit': 'ecb05cbbd68717e415f69df2ac488c1d323b1da3'}, {'repository': 'Legacy.Maliev.CompatibilityContracts', 'commit': '78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7'}, {'repository': 'Legacy.Maliev.ProcurementService', 'commit': None}], 'defaultsAdoption': {'previousDefaults': '7edcd961024868513fd5f373cab3dcb261197f77', 'reviewedDefaults': 'ecb05cbbd68717e415f69df2ac488c1d323b1da3', 'acceptedConsumerMain': '9c80113e76c0b209b3be113c400e3c24a460d5e6', 'scope': 'Shared token-owner deadline and additive typed-response helpers only; all52 Procurement production/build/public fixture inputs and Auth/Contracts pins unchanged', 'localGuards': 'Existing workload admission/body guard, late response owner, named client10s and normal IAM composition unchanged', 'priorGraph': 'public-graph-accepted-9c801.json', 'nativeAcceptance': 'Pending fresh Procurement full/focused and actual Auth Program join; prior accepted consumer evidence is historical'}, 'expectedCases': 15, 'expectedMethods': {'Procurement.AuthProgram.Tests.AuthProgramProcurementJoinTests.RealEmployeeAndWorkloadEndpoints_LiveCreateThenFreshDeny': 1, 'Procurement.AuthProgram.Tests.AuthProgramProcurementJoinTests.RealWorkloadBearer_SupplierDeleteUsesEmployeeAndExactResource': 2, 'Procurement.AuthProgram.Tests.AuthProgramProcurementJoinTests.ActualProducerRefusalOrConsumerTrustFailure_CannotPersist': 8, 'Procurement.AuthProgram.Tests.OwnedCleanupTests.FailureAtAnyPosition_StillAttemptsEveryOwnedResource': 3, 'Procurement.AuthProgram.Tests.OwnedCleanupTests.MultipleFailures_PreserveFirstExceptionAndAttemptRemainingResources': 1}, 'fixtureEnrollment': 'explicit synthetic client with iam.auth.check-permission in test configuration only', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False, 'previousMasterQuerySourceChange': {'baseCommit': '26da4a1804c0a5833890e975680ee569c3aa4094', 'path': 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs', 'baseBlob': '7c9342bf642f71cbf5087371377ebd46c960ee61', 'candidateBlob': '87602ce7789dc1b5c27ca19ed1c6e8d12d292e00', 'unchangedInputCount': 51, 'unchangedInputSha256': '657ee76ed5af1272c2b21217ebe0145296f6d9aed774e5780422cb4ca5e5142c'}, 'nullableSortProducerAdvance': {'previousProcurement': '8f2c5fc0678734e3240ce368b30e26db858e63d4', 'reviewedProcurement': 'da6af357254f1e42d95ce592bc716b2ae0abb4cf', 'acceptedConsumerMain': '3be3bb1567edc1135cafd84de80b3ea69b281276', 'inputCount': 52, 'changedInput': 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs', 'previousBlob': '87602ce7789dc1b5c27ca19ed1c6e8d12d292e00', 'reviewedBlob': '79f6cbb8e70980e7ae48e0825a4a717f410ae09b', 'unchangedInputCount': 51, 'unchangedInputSha256': '657ee76ed5af1272c2b21217ebe0145296f6d9aed774e5780422cb4ca5e5142c', 'scope': 'Eight nullable supplier name/date and purchase-order CreatedDate branches preserve SQLServer NULL-first ASC/NULL-last DESC; ID tie order deliberately stabilizes paging', 'stablePagingDecision': 'Source only specifies the selected field; ascending ID tie order is a deliberate deterministic paging choice, not a claim of original SQLServer tie order', 'excluded': 'Search, page50/cap250, enums, Defaults76, authority composition and immutable public runtime fixture unchanged; global collation parity is separate', 'independentReview': 'Coordinator read complete one-input patch and24 normal authenticated HTTP/owned PostgreSQL cases with explicit postinsert storedNULL assertions on 2026-10-06', 'nativeAcceptance': 'Pending fresh full293, nullable24, lifecycle48, query19, deadline6, actualAuth15 plus9 guard controls; no RED baseline executed'}, 'literalObjectNameProducerAdvance': {'previousProcurement': 'da6af357254f1e42d95ce592bc716b2ae0abb4cf', 'reviewedProcurement': '30333914eaaa7cd508a3874169f29003e627d055', 'acceptedConsumerMain': '30a46c2eb7f1a8ef630440d2aaec4aa72e6bf7dc', 'inputCount': 52, 'changedInput': 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs', 'previousBlob': '79f6cbb8e70980e7ae48e0825a4a717f410ae09b', 'reviewedBlob': 'bd3729e337f5b9b0a8507875734bf3da2273a594', 'unchangedInputCount': 51, 'unchangedInputSha256': '657ee76ed5af1272c2b21217ebe0145296f6d9aed774e5780422cb4ca5e5142c', 'scope': 'Create and update preserve literal ObjectName; blank validation, Bucket trimming, ownership, timestamps and provider behavior unchanged', 'sourceCommit': '135e526d0dab85c415b3afdcefd7b70fe2c82e2f', 'sourcePath': 'Maliev.PurchaseOrderService.Api/Controllers/FilesController.cs', 'sourceBlob': '158240d27dd9119b88599c6e7f5294c77d948cfe', 'independentReview': 'Coordinator FULL and notification_join_review approved complete three-file literal-value patch on 2026-10-06; graph advance awaiting separate FULL review', 'nativeAcceptance': 'Pending corrected-head full293, nullable24, lifecycle48, query19, deadline6, actualAuth15 plus9 unchanged guard controls; initial3033391 auth join stopped at stale graph preflight before native tests', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'previousIntentionalSourceChange': {'baseCommit': '26da4a1804c0a5833890e975680ee569c3aa4094', 'path': 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs', 'baseBlob': '7c9342bf642f71cbf5087371377ebd46c960ee61', 'candidateBlob': 'bd3729e337f5b9b0a8507875734bf3da2273a594', 'unchangedInputCount': 51, 'unchangedInputSha256': '657ee76ed5af1272c2b21217ebe0145296f6d9aed774e5780422cb4ca5e5142c'}, 'intentionalSourceChanges': {'previousProcurement': '4a117fb68cebffc9e0acae9000750e8e45ec62cc', 'reviewedProcurement': None, 'inputCount': 82, 'changedInputs': {}, 'unchangedInputCount': None, 'unchangedInputSha256': None, 'productionBuildInputCount': 66, 'productionBuildInputSha256': '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'previousStringIntentionalSourceChanges': {'previousProcurement': '30333914eaaa7cd508a3874169f29003e627d055', 'reviewedProcurement': 'd4b08faf07c684c3d4f8c75280486379d72532e2', 'inputCount': 57, 'changedInputs': {'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs': {'previousMetadata': '100644 blob af10f45f034ce61e5563db4efaec3321dfe19bb6', 'reviewedMetadata': '100644 blob 03c411035df3b6268972792e0df835534aec1fc1'}, 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs': {'previousMetadata': '100644 blob 24abc1218fc64d54516cd673eb050d8fef08a85d', 'reviewedMetadata': '100644 blob 63dfa7c375090e0a1d3dd191f7430b1519c8bdea'}, 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 2e68e9f383160dfe6082f7a23b859bfbf5b2d325'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 143e1ae02a1fd1100eb2d75dce9b8124188e4cd4'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 1663bacce0bf61de8db5688a82e48354c24ba658'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs': {'previousMetadata': '100644 blob 96e49d663dced4fe3c20ed48bd720de7ed881569', 'reviewedMetadata': '100644 blob e583ebd59e3b43b03ae68bbe91cf8abdfd763da8'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob a36060169d6812f83f1fe764faddc0c0eeee2fea'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 8c82219082c3a6f2bb629a65d72d8a459b07b5d4'}, 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs': {'previousMetadata': '100644 blob c4a01d77144bdac6530d570481a55130dc86474d', 'reviewedMetadata': '100644 blob e77cced2826569ba96cb46d659e0fb90be8ceb0e'}, 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs': {'previousMetadata': '100644 blob dbf7a31e550aceedf44c91f1b61117cbd4392f75', 'reviewedMetadata': '100644 blob b025a7b1939af8e27474f7b978a49a076143638c'}, 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': {'previousMetadata': '100644 blob bd3729e337f5b9b0a8507875734bf3da2273a594', 'reviewedMetadata': '100644 blob 62276afe71d6a0513747be48d88760ee087d0cc4'}}, 'unchangedInputCount': 46, 'unchangedInputSha256': '103ee14726c927353d9279e55613baad56767b195e2bc105e96b1c63729c948b', 'sourceReviewReceiptSha256': 'cc5b1cc25d124609b47b81b09875ad8fdf6a60d9ef43acac26eb9d135575d3c5', 'scope': 'FULL18 reviewed owned string requiredness/UTF16/File JSON PUT source only; six changed and five added runtime inputs; peer pins and public fixture unchanged', 'nativeAcceptance': 'Pending corrected candidate actualAuth15/full309/focus16/legacy5 plus guard controls', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'previousLiteralIntentionalSourceChanges': {'previousProcurement': 'd4b08faf07c684c3d4f8c75280486379d72532e2', 'reviewedProcurement': 'cf114bcac6e4aa041ca51ec1e60739e868c8da06', 'inputCount': 57, 'changedInputs': {'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs': {'previousMetadata': '100644 blob e70c82d5841b83c3fb841bd7a3e45693c76d1275', 'reviewedMetadata': '100644 blob 91b6bf11646f89f5c6736e7f54af964e044ae6ed'}, 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': {'previousMetadata': '100644 blob 62276afe71d6a0513747be48d88760ee087d0cc4', 'reviewedMetadata': '100644 blob 34aead52a4555030d73da312dde868a3b58170c9'}, 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': {'previousMetadata': '100644 blob c879519e879d91f4556962e0668db9a5b40e1c48', 'reviewedMetadata': '100644 blob 13bef56d1b51a1df43fffe2e48967bd4e6f16ba2'}}, 'unchangedInputCount': 54, 'unchangedInputSha256': '865371657e11db227ea83813eb85b5d72a471fd1a02b4ccccae128f5a9f08c71', 'sourceReviewReceiptSha256': '646a525c02b72d91ee12285d08b611cc25a2cb2f57d2790b39aa825a19d40236', 'runtimeNativeAdmissionSha256': '045225728e27a8a46ac1b01f5f5b3abcf480fb176d57dff8abe9f4919414ef54', 'scope': 'Reviewed literal controller/repository copies and public runtime literal expectation only; three changed inputs and54 unchanged. Peer pins unchanged.', 'nativeAcceptance': 'Owned seven literal cases passed; final full316/Auth15/all8 native candidate acceptance pending', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'historicalGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph.json', 'sha256': '205063c79697948343ba659b13757b68ef4814d1b62861484a1dd90c0b8e7d41', 'role': 'Immutable historical supplier primitive/string source witness; not current child-replay runtime admission', 'procurement': 'c40fd246c17b738879c9345c6bcca44d96faf025'}, 'previousSupplierPrimitiveIntentionalSourceChanges': {'previousProcurement': 'cf114bcac6e4aa041ca51ec1e60739e868c8da06', 'acceptedBase': '209227c7f6f580946853c395f0fafccec59b65a7', 'reviewedProcurement': 'c40fd246c17b738879c9345c6bcca44d96faf025', 'inputCount': 58, 'changedInputs': {'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': {'previousMetadata': '100644 blob 615ca9428c7d72cf1e4f9dbfc6dde8b58578cddf', 'reviewedMetadata': '100644 blob f93920a8e93454b7f5538c60a18134c0dee892a1'}, 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob 25834e7c9705786777a707734b914fbf99987cfc'}}, 'unchangedInputCount': 56, 'unchangedInputSha256': '9c8143319715c5030eac466add24466f5a6cbb2235ea244e5d14f3018470d914', 'sourceReviewReceiptSha256': '372c81df7dbbb0b1f351bc060e7d40abfd1b0b41eba0b3de7a90ad3c0f01bce0', 'scope': 'Only reviewed Supplier request model and added local converter; all other runtime/build/public fixture inputs and external Auth/Defaults/Contracts pins unchanged', 'nativeAcceptance': 'NOT RUN on successor; exact hosted full365 and actual Auth15 required', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'credentialCorrection': {'reviewedProcurement': 'f22c67f94f7641856fa27a1d94c7fa55081f6bf7', 'sourceReceiptSha256': 'f7d3959deba32735b77b75c3633a26be93165b5da76363b7a4b3ef039ff52453', 'scope': 'One non-runtime-inventory integration test fixture line;64 runtime/build/publicfixture inputs unchanged from reviewed production2ff'}, 'compilerCorrection': {'reviewedProcurement': '37664f6466babad471f7b007bb8c2f5c9e3a2032', 'sourceReceiptSha256': 'af9398b239d451c7bd43ae24829ee7a7b73da7e9d1b87133e799fcd768b28953', 'scope': 'One migration designer XMLcomment runtimeblob and3 constantSQLtestcalls;64inputs/13changed/51unchanged retained; local corrected buildNOTRUN afterfreshmemoryguardfailure'}, 'runtimeCorrection': {'reviewedProcurement': '99049bab2c100ffdf6606bf11a2f50980c0cf3cf', 'sourceReceiptSha256': 'c603bfce2a064f6f4e68e8fb708798e9b8d0df9ec911aa463b6da26a6a1f7b2c', 'localValidationSealSha256': 'a1b0805e62586b6faa12ac8d330e27d014d0383fda83f93e07c24ea83cab8569', 'scope': 'Fresh read-only snapshot execution strategy; actual closed-port refusal host; original string migration witness. All58 cases retained; current64inputs/13changed51unchanged. Hosted990 full443 pending.'}, 'previousAcceptedGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json', 'sha256': 'd4aab5b24027fb666b8571c67450c59cd6b188970b34818fa308b34e215edd1a', 'inputCount': 64, 'procurement': '99049bab2c100ffdf6606bf11a2f50980c0cf3cf', 'role': 'Immutable accepted default-off child replay witness; historical custody retained'}, 'latestAcceptedSupplierGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-address.json', 'sha256': '15aefdb6d7d587b3ca9c6c9183f732dc85ab8df0974a8b6ab1f416f7adc73177', 'procurement': '574b3b6ccecb4e4df9c4e72c326d9fb7f9a918f5', 'inputCount': 65, 'role': 'Immutable accepted supplier-address65 witness; original supplier converter and child replay retained'}, 'previousBucketIntentionalSourceChanges': {'previousProcurement': '574b3b6ccecb4e4df9c4e72c326d9fb7f9a918f5', 'acceptedBase': '3ef85c3f867b70b2321fae41ca764ddcfd898b45', 'reviewedProcurement': '232211084ce15682391036fbbbe777c6c723e773', 'inputCount': 66, 'changedInputs': {'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': {'previousMetadata': '100644 blob 34aead52a4555030d73da312dde868a3b58170c9', 'reviewedMetadata': '100644 blob e3e6d902b10d7b985f12bb5d852982313cb13884'}, 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob c182f47f50e92fd3225c08d14bcb505e49d73ad5'}}, 'unchangedInputCount': 64, 'unchangedInputSha256': '1209fd14caf59bcb5cefd7c41d031e9315567e61115f1adce62c319309156d3b', 'sourceReviewReceiptSha256': 'b4b615681ce2b2379675a5f4b09ecc67eb40cbc77f25abcafe37cc70cdbd3aad', 'scope': 'Only two reviewed Data bucket-guard inputs;64 runtime/build/public-fixture inputs unchanged; accepted supplier converters and child replay retained', 'nativeAcceptance': 'NOT RUN on graph successor; original source-head Auth refused before tests; exact successor actualAuth15/full493/focus27 and unchanged ordinary gates required', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'latestAcceptedBucketGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-file-bucket.json', 'sha256': 'd5890949f9f397c16fc3ca225993946f9abf8efef866c20e82653210724884a8', 'procurement': '232211084ce15682391036fbbbe777c6c723e773', 'inputCount': 66}, 'previousPurchaseOrderAddressIntentionalSourceChanges': {'previousProcurement': '232211084ce15682391036fbbbe777c6c723e773', 'acceptedBase': '3db81d32edf424c712009f7b631d93b0b8724f3d', 'reviewedProcurement': '430d2cabbdaa712e3536a119abe88f9167021358', 'inputCount': 67, 'changedInputs': {'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': {'previousMetadata': '100644 blob 53c78576a1ca7f8ca2ce361446cc6d14f7d4a60c', 'reviewedMetadata': '100644 blob f20b6e2ac31e8a4e91567fca14cf6af449e3b3f0'}, 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs': {'previousMetadata': None, 'reviewedMetadata': '100644 blob cdbfc2e43f4d8575006df249836145cf7ecb50d6'}}, 'unchangedInputCount': 65, 'unchangedInputSha256': 'f83b7cc0ade6e5f92e0fca40188d56f4021cd8072932609bc6a3cf59c982b48c', 'sourceReviewReceiptSha256': '93d63cc7cf9a9a327983c040ccc55f4baca379a53ed325a48e1f4f926c2dfd83', 'scope': 'Only two reviewed purchase-order address Application inputs; 65 runtime/build/public-fixture inputs unchanged, including bucket guard and supplier converters', 'nativeAcceptance': 'NOT RUN on successor; new32/full525 forecast with exact493 retention and actualAuth15 plus unchanged gates required', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'latestAcceptedPurchaseOrderAddressGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-purchase-order-address.json', 'sha256': '9ac11ba51211e1c17cde9385bb31f8e952eef302892233c867c8e04c64bb5c0a', 'procurement': '430d2cabbdaa712e3536a119abe88f9167021358', 'inputCount': 67}, 'previousFixtureIntentionalSourceChanges': {'previousProcurement': '430d2cabbdaa712e3536a119abe88f9167021358', 'acceptedBase': 'f84d493ea3cbfd9667d1a2e2a31fabebfc0bba93', 'reviewedProcurement': '1e520e795ec534ac9512ccf1bdb272a34e5140e9', 'inputCount': 67, 'changedInputs': {'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': {'previousMetadata': '100644 blob 13bef56d1b51a1df43fffe2e48967bd4e6f16ba2', 'reviewedMetadata': '100644 blob a17ef270d1a0225fda879aef990b2dab01e73dec'}}, 'unchangedInputCount': 66, 'unchangedInputSha256': '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443', 'sourceReviewReceiptSha256': '2445b28bc13637d7b31c29e94e341da500f7246bf9183c4300004b42dc52d131', 'scope': 'One reviewed public test-fixture input; all 66 production/build inputs unchanged; provider containment remains unqualified until actual cleanup and expiry observations', 'nativeAcceptance': 'NOT RUN: Release/focused18/full543 forecast retaining exact525/Auth15 and unchanged gates; strict receipt parser and independent outer-process/session cleanup witness required', 'productionEnrollmentProven': False, 'productionIamBridgeProven': False, 'wholeInitialSourceParityClosed': False}, 'previousReviewedFixtureGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-containment.json', 'sha256': '1dfc57fa5a10f49b16f224e6f04b0a1355c75996ae9f624fdaec5e27913b6d64', 'procurement': '1e520e795ec534ac9512ccf1bdb272a34e5140e9', 'inputCount': 67, 'qualification': 'Reviewed draft source only; native fixture containment not accepted'}, 'previousReviewedStartupDiagnosticGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-diagnostics.json', 'sha256': 'f8c54c39bf4e81c0674001e47993faa0f0ab2d8e281d2170cc508ba6e50c1a24', 'procurement': '61746f2fe03fd71eb3f208bfbf861eef800b9599', 'inputCount': 67, 'qualification': 'Reviewed source custody only; predecessor native claims remain separate'}, 'previousReviewedStartupJournalGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-startup-journal.json', 'sha256': 'b93372915b0a1a9b84426576baaec1c443437fdb2bc10804df5d93b83ca169ec', 'procurement': '24099f8e88ea14eebfa9a995dcd5f7569dad3dbf', 'inputCount': 69, 'qualification': 'Immutable predecessor source custody; native scope stays separate'}, 'ownerCorrelationSourceBinding': {'reviewedProducer': '4a117fb68cebffc9e0acae9000750e8e45ec62cc', 'inputMetadata': {'Directory.Build.props': '100644 blob b47c8d23651f11ea8366bb63f4520fb8de6c6df3', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs': '100644 blob 1bad18d6797295124d84083ba7f5e93276124c1e', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementPermissions.cs': '100644 blob 58a5a184edc50559048dd4b0329b80b5a6a57b5f', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementWorkloadExchangeGuard.cs': '100644 blob 2cbafd5644b7653a1eb323788be8f95bd98337ad', 'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs': '100644 blob 5382d06a862ff843bbb01539ddd8822070e86757', 'Legacy.Maliev.ProcurementService.Api/Controllers/OrderItemsController.cs': '100644 blob d5e94258bed07bff6c4c915ab4cb1e34fa368902', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs': '100644 blob 91b6bf11646f89f5c6736e7f54af964e044ae6ed', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrdersController.cs': '100644 blob 19530897851dcd97dbf52ee71d297f0b4cd0517c', 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs': '100644 blob 63dfa7c375090e0a1d3dd191f7430b1519c8bdea', 'Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs': '100644 blob f7549641da035088c553d07e42202c73ea881512', 'Legacy.Maliev.ProcurementService.Api/Dockerfile': '100644 blob b2c525d395006937f2faf1dbbe0ffa53b669e6d0', 'Legacy.Maliev.ProcurementService.Api/DurableChildCreateEndpoint.cs': '100644 blob 84b6da4468a7a22ae10d81aed8b29f6dab15dfaf', 'Legacy.Maliev.ProcurementService.Api/DurableCreateEndpoint.cs': '100644 blob 4a723a638129fbdb99a17758a06a8cd5c3f026ac', 'Legacy.Maliev.ProcurementService.Api/IdempotentCreates.cs': '100644 blob c8a0e7f92a10b833cd5a5254b0253f7537b67074', 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': '100644 blob 0fefb94217cd594e097c2e7aaee24da28b7c8c56', 'Legacy.Maliev.ProcurementService.Api/Program.cs': '100644 blob 19d17888cd77004b42f290a3c0daad454dfd4b5e', 'Legacy.Maliev.ProcurementService.Api/Properties/launchSettings.json': '100644 blob 5b49ab6aa8f800b7ed4a376abb9ccf0942625251', 'Legacy.Maliev.ProcurementService.Api/appsettings.Development.json': '100644 blob 0c208ae9181e5e5717e47ec1bd59368aebc6066e', 'Legacy.Maliev.ProcurementService.Api/appsettings.json': '100644 blob b057873ee272efdfc5311a0179a6214f4e1768b7', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementChildCreates.cs': '100644 blob b3cda03315eb9e70d9264a5a50fbdbfeef6c3705', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementCreates.cs': '100644 blob b91e35948db367bb5279029e5838a0e87617041c', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs': '100644 blob 90c2628be1aceef0178533add09fdea7efa4c42a', 'Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj': '100644 blob 8f5ac62cbd3b2f8cf8370a899a575e25d4a07dab', 'Legacy.Maliev.ProcurementService.Application/Models/DurableCreateModels.cs': '100644 blob 6fce05a93ea834e1fc661e0938456e92b908a003', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': '100644 blob f20b6e2ac31e8a4e91567fca14cf6af449e3b3f0', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementTransactionUncertainException.cs': '100644 blob 6486a812e5e78ae8e8be9bcf54ee8683989e0615', 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs': '100644 blob cdbfc2e43f4d8575006df249836145cf7ecb50d6', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs': '100644 blob a450e196d981d66aef98b6a5970e6f1f53bcef67', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs': '100644 blob 25834e7c9705786777a707734b914fbf99987cfc', 'Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs': '100644 blob 9b17fd46fce25162e30854210a1f945a1f9d6f48', 'Legacy.Maliev.ProcurementService.Data/ChildReceiptRecords.cs': '100644 blob 8974e76d5c72762828a0d32624a09faaafe8dda4', 'Legacy.Maliev.ProcurementService.Data/CreateReceiptRecord.cs': '100644 blob 7df3a2a661854d928fb4ac6363596546419ffeb3', 'Legacy.Maliev.ProcurementService.Data/DistributedProcurementCache.cs': '100644 blob cd88f078148dadf470850b383874f2453c3ab146', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementChildCreates.cs': '100644 blob 0fe45073973624adcf21d6abcef8a23ced035f97', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementCreates.cs': '100644 blob d8e7d7f4182fc613a399990acf9109f0ca7a9e3a', 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': '100644 blob c152c047af1ddb1bcedccf08b25d6a03320d34f3', 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs': '100644 blob 2e68e9f383160dfe6082f7a23b859bfbf5b2d325', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.Designer.cs': '100644 blob ff647d92152d6acaa1b5d54c2381711263a6e38a', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.cs': '100644 blob f27917f143b0cbdf2809881b96c2ccce3b4dccb8', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.Designer.cs': '100644 blob 2e9588ac6e0a9da4feaa4fb59a683f785560c713', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs': '100644 blob 86049cb052f1390dad51c9800f301d2af411a87f', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.Designer.cs': '100644 blob 9ab941b4fbbc26b1bf4277328792cc594936e7ca', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.cs': '100644 blob 8b1f910f078b8a4d13f15c6903a9825e0198bbbf', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs': '100644 blob 143e1ae02a1fd1100eb2d75dce9b8124188e4cd4', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs': '100644 blob 1663bacce0bf61de8db5688a82e48354c24ba658', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.Designer.cs': '100644 blob 71271d8755686ea6609b0d794484ec8ae29e41eb', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.cs': '100644 blob 2ba84b62673cd157fd53807eeb21bb9c59375422', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs': '100644 blob b3477b7823f63b37bed92959f7100e3cd287baf9', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.Designer.cs': '100644 blob 84c0f1841ecd125e52dbdd8fff6d560cf26baab7', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.cs': '100644 blob 2d36ff6600a6c973baf717fe07c61e72a3cad80e', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.Designer.cs': '100644 blob 7edb0df2fe539c86629d0296e95ae428506d2a90', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs': '100644 blob f6c70ffcb468140850659ff2dee07290d5b891b4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.Designer.cs': '100644 blob 022a0c30e60b669e22b310ba6f589244f4d004fa', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.cs': '100644 blob 653202333c192a7c96844f639858f9e362524d77', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs': '100644 blob a36060169d6812f83f1fe764faddc0c0eeee2fea', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs': '100644 blob 8c82219082c3a6f2bb629a65d72d8a459b07b5d4', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs': '100644 blob e77cced2826569ba96cb46d659e0fb90be8ceb0e', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContextFactories.cs': '100644 blob 0eadcec30749cdccde9c4a8eae39e5f9c9a0ec80', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs': '100644 blob 1a8487f24a647a186258d487b84e1cc08fa7d83b', 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': '100644 blob e3e6d902b10d7b985f12bb5d852982313cb13884', 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs': '100644 blob c182f47f50e92fd3225c08d14bcb505e49d73ad5', 'Legacy.Maliev.ProcurementService.Data/ReceiptReadiness.cs': '100644 blob 7e252a2a88928f12d421b10fe7cf831146268b9d', 'Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj': '100644 blob 51addf44ecf979d69d9d77527d402f14c06a4fa5', 'Legacy.Maliev.ProcurementService.Domain/ProcurementEntities.cs': '100644 blob 141a05708c3374afe8ad9471698a892addbf2531', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs': '100644 blob 6f9ab7b766565ceba5522e53df39cd4008c38a7e', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs': '100644 blob 43ea0949935b0486d8932c927cad90ab8a1ccb3d', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': '100644 blob a4fda2edca34c7e8f918d8c43edd72438ed66f05', 'Legacy.Maliev.ProcurementService.slnx': '100644 blob 48c1f4ac9b6141df5596bcdc99eb0b22b4a1213e', 'nuget.config': '100644 blob 765346e5343d46ac83654843869dc06b65b2bdc4', 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': '100644 blob 82894df31a17ed37a3ff453fbfa27818c34eecc2', 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': '100644 blob 3d6a4b8d2979c3daad819cf0e764fcdd26dd71f6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': '100644 blob 1fb3433cb2bb99b38367da14e4c49e8f1cc004a6', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': '100644 blob c5c7911f988340e12921156496893ecacc0f1489', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': '100644 blob 281a7f13123f16a96cacd2d9465d909c0c07bae0', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs': '100644 blob 67346c8762a43d2008a18ae47064e0353a9997bc', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs': '100644 blob f710b2a0f435eb2b6f648ee9cf2c15a5a0d57058', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs': '100644 blob 432386cd0e1557860431bef87345c66fbe9ef41a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs': '100644 blob 561e3c5eeb9ddf8cabc997b14a5aa4f36af2fcfe', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': '100644 blob e180274800334e331a8f0ae4fed73bc10b84328a', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs': '100644 blob 2ec6c2d9b59bb8cf3b6035005489acba1589c4b2'}, 'releaseAllowed': True}, 'schemaVersion': 2, 'previousReviewedOwnerCorrelationGraph': {'path': 'tools/ProcurementAuthProgram.Tests/public-graph-fixture-owner-correlation-v1.json', 'sha256': '5394705469105e1b020f4a7fe44247964605fe7c9e6cad51177c7667a1dd5b23', 'procurement': '4a117fb68cebffc9e0acae9000750e8e45ec62cc', 'fixtureInputCount': 14, 'inputCount': 80}, 'diagnosticDependencySourceBinding': {'reviewedProducer': None, 'releaseAllowed': False, 'fixturePaths': ['Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableOwnedFixtureWrappers.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureConnectionObserver.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelation.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureOwnerCorrelationTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournal.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementFixtureStartupJournalTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeOwnedFixtureWrappers.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableDiagnosticPolicy.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableDiagnosticPolicyTests.cs'], 'fixtureInputCount': 16, 'inputCount': 82, 'productionBuildInputCount': 66, 'productionBuildInputSha256': '115556e55d729910cad1792c7d91297b65a03336b6de74a2aeee5b62447b1443', 'inputMetadata': {}}}


def strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError('Nonfinite JSON value: ' + value)

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    require_finite_json(value)
    return value


def require_finite_json(value):
    import math
    if type(value) is float and not math.isfinite(value):
        raise ValueError('Nonfinite JSON number')
    if type(value) is dict:
        for child in value.values():
            require_finite_json(child)
    elif type(value) is list:
        for child in value:
            require_finite_json(child)


def require_typed_equal(actual, expected):
    require_finite_json(actual)
    if type(actual) is not type(expected):
        raise ValueError('Frozen JSON type drift')
    if type(expected) is dict:
        if actual.keys() != expected.keys():
            raise ValueError('Frozen JSON keys drift')
        for key in expected:
            require_typed_equal(actual[key], expected[key])
    elif type(expected) is list:
        if len(actual) != len(expected):
            raise ValueError('Frozen JSON array length drift')
        for left, right in zip(actual, expected):
            require_typed_equal(left, right)
    elif actual != expected:
        raise ValueError('Frozen JSON value drift')


_historical_owner_graph = require_owner_graph
_historical_owner_inputs = require_owner_inputs
_historical_inputs = inputs
_historical_results = results
_historical_tracked_inputs = tracked_inputs


def frozen_historical_graph():
    raw = (ROOT / OWNER_PREDECESSOR_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != OWNER_PREDECESSOR_SHA256:
        raise ValueError('Historical owner80 predecessor byte custody drift')
    value = strict_json(raw)
    # Historical producer controls may independently patch the historical constant.
    # Runtime callers cannot supply a producer or downgrade mode.
    for entry in value['references']:
        if entry['repository'] == 'Legacy.Maliev.ProcurementService':
            entry['commit'] = REVIEWED_CORRELATION_PRODUCER
    value['ownerCorrelationSourceBinding']['reviewedProducer'] = REVIEWED_CORRELATION_PRODUCER
    value['intentionalSourceChanges']['reviewedProcurement'] = REVIEWED_CORRELATION_PRODUCER
    return value


def require_diagnostic_graph(manifest, *, source_only=False):
    require_typed_equal(manifest, FROZEN_DIAGNOSTIC_GRAPH)
    predecessor = frozen_historical_graph()
    _historical_owner_graph(predecessor)
    binding = manifest['diagnosticDependencySourceBinding']
    require_typed_equal(binding['fixturePaths'], list(DIAGNOSTIC_PATHS))
    require_typed_equal(binding['fixtureInputCount'], 16)
    require_typed_equal(binding['inputCount'], 82)
    require_typed_equal(binding['productionBuildInputCount'], 66)
    require_typed_equal(manifest['expectedCases'], predecessor['expectedCases'])
    require_typed_equal(manifest['expectedMethods'], predecessor['expectedMethods'])
    external = lambda graph: [entry for entry in graph['references'] if entry['repository'] != 'Legacy.Maliev.ProcurementService']
    require_typed_equal(external(manifest), external(predecessor))
    for field in ('productionEnrollmentProven', 'productionIamBridgeProven', 'wholeInitialSourceParityClosed'):
        require_typed_equal(manifest[field], False)
    entries = [entry for entry in manifest['references'] if entry['repository'] == 'Legacy.Maliev.ProcurementService']
    if len(entries) != 1:
        raise ValueError('Exactly one Procurement producer required')
    if DIAGNOSTIC_PRODUCER is None:
        require_typed_equal(binding['reviewedProducer'], None)
        require_typed_equal(binding['releaseAllowed'], False)
        require_typed_equal(binding['inputMetadata'], {})
        require_typed_equal(entries[0]['commit'], None)
        if not source_only:
            raise ValueError('Diagnostic82 producer unbound; native admission forbidden')
        return
    if type(DIAGNOSTIC_PRODUCER) is not str or re.fullmatch('[0-9a-f]{40}', DIAGNOSTIC_PRODUCER) is None:
        raise ValueError('Noncanonical diagnostic producer')
    require_typed_equal(binding['reviewedProducer'], DIAGNOSTIC_PRODUCER)
    require_typed_equal(entries[0]['commit'], DIAGNOSTIC_PRODUCER)
    require_typed_equal(binding['releaseAllowed'], True)
    metadata = binding['inputMetadata']
    if len(metadata) != 82 or any(path not in metadata for path in DIAGNOSTIC_PATHS):
        raise ValueError('Exact82 selected dependency inputs required')
    production = {path: value for path, value in metadata.items() if path not in DIAGNOSTIC_PATHS}
    require_typed_equal(production, {path: value for path, value in FROZEN_OWNER_INPUT_METADATA.items() if path not in FIXTURE_INPUTS})
    digest = hashlib.sha256(json.dumps(production, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    require_typed_equal(digest, PRODUCTION_BUILD_SHA256)
    change = manifest['intentionalSourceChanges']
    require_typed_equal(change['reviewedProcurement'], DIAGNOSTIC_PRODUCER)
    require_typed_equal(change['previousProcurement'], REVIEWED_CORRELATION_PRODUCER)
    require_typed_equal(change['inputCount'], 82)
    require_typed_equal(change['productionBuildInputCount'], 66)
    require_typed_equal(change['productionBuildInputSha256'], PRODUCTION_BUILD_SHA256)
    actual_changes = {path: {'previousMetadata': FROZEN_OWNER_INPUT_METADATA.get(path), 'reviewedMetadata': value,
                            'classification': 'Test-only diagnostic dependency; no native qualification'}
                      for path, value in metadata.items() if FROZEN_OWNER_INPUT_METADATA.get(path) != value}
    require_typed_equal(change['changedInputs'], actual_changes)
    require_source_change(metadata, manifest)


def resolve_contract(manifest, *, source_only=False):
    require_finite_json(manifest)
    if type(manifest) is not dict:
        raise ValueError('Manifest must be an object')
    if manifest.get('graphId') == FROZEN_DIAGNOSTIC_GRAPH['graphId']:
        require_diagnostic_graph(manifest, source_only=source_only)
        return 'diagnostic-v2'
    historical = frozen_historical_graph()
    if manifest.get('graphId') == historical['graphId']:
        require_typed_equal(manifest, historical)
        _historical_owner_graph(manifest)
        return 'owner-v1'
    raise ValueError('Unknown schema/graph/producer combination')


def require_owner_graph(manifest):
    resolve_contract(manifest)


def require_owner_inputs(current, reviewed, manifest):
    mode = resolve_contract(manifest)
    if mode == 'owner-v1':
        _historical_owner_inputs(current, reviewed, manifest)
        return
    expected = manifest['diagnosticDependencySourceBinding']['inputMetadata']
    require_typed_equal(current, expected)
    require_typed_equal(reviewed, expected)
    require_source_change(expected, manifest)


def git_read(repository, *arguments, binary=False):
    result = subprocess.run(['git', '-C', str(repository), *arguments], check=True,
                            capture_output=True, timeout=15)
    return result.stdout if binary else result.stdout.decode('utf-8').strip()


def diagnostic_tracked_inputs(repository, revision='HEAD'):
    selected = {}
    raw = git_read(repository, 'ls-tree', '-r', '-z', revision, binary=True)
    for record in raw.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        path = name.decode('utf-8')
        if path in DIAGNOSTIC_PATHS or any(path.startswith(project + '/') for project in PROJECTS) or (
                '/' not in path and any(fnmatch.fnmatchcase(path.lower(), pattern) for pattern in PATTERNS)):
            selected[path] = metadata.decode('ascii')
    return selected


def require_git_admission(joined_root, manifest, owned_head, source_head):
    resolve_contract(manifest)
    if manifest['graphId'] != FROZEN_DIAGNOSTIC_GRAPH['graphId']:
        raise ValueError('Current CLI cannot downgrade to historical admission')
    for value in (owned_head, source_head):
        if type(value) is not str or re.fullmatch('[0-9a-f]{40}', value) is None:
            raise ValueError('Exact owned/source commit evidence required')
    if git_read(ROOT, 'rev-parse', 'HEAD') != owned_head:
        raise ValueError('Owned HEAD mismatch')
    if git_read(ROOT, 'rev-parse', '--is-shallow-repository') != 'false':
        raise ValueError('Complete owned history required')
    for before, after in ((DIAGNOSTIC_PRODUCER, source_head), (source_head, owned_head)):
        git_read(ROOT, 'merge-base', '--is-ancestor', before, after)
    for entry in manifest['references']:
        repository = joined_root / entry['repository']
        if git_read(repository, 'rev-parse', 'HEAD') != entry['commit']:
            raise ValueError('External producer HEAD mismatch: ' + entry['repository'])
        if entry['repository'] == 'Legacy.Maliev.ProcurementService' and git_read(repository, 'rev-parse', '--is-shallow-repository') != 'false':
            raise ValueError('Complete producer history required')
    expected = manifest['diagnosticDependencySourceBinding']['inputMetadata']
    witness = joined_root / 'Legacy.Maliev.ProcurementService'
    require_typed_equal(diagnostic_tracked_inputs(ROOT), expected)
    require_typed_equal(diagnostic_tracked_inputs(ROOT, DIAGNOSTIC_PRODUCER), expected)
    require_typed_equal(diagnostic_tracked_inputs(witness), expected)
    for path in expected:
        committed = git_read(ROOT, 'show', DIAGNOSTIC_PRODUCER + ':' + path, binary=True)
        if (ROOT / path).read_bytes() != committed or (witness / path).read_bytes() != committed:
            raise ValueError('Selected working bytes differ: ' + path)


def inputs(root, manifest, *, owned_head=None, source_head=None):
    mode = resolve_contract(manifest)
    if mode == 'owner-v1':
        _historical_inputs(root, manifest)
        return
    require_git_admission(root, manifest, owned_head, source_head)
    print(json.dumps({'graphId': manifest['graphId'], 'identicalRuntimeBuildFixtureInputs': 82,
                      'nativeExecuted': False, 'qualification': False}, allow_nan=False))


def results(root, manifest, *, joined_root=None, owned_head=None, source_head=None):
    mode = resolve_contract(manifest)
    if mode == 'diagnostic-v2':
        if joined_root is None:
            raise ValueError('Results require the same joined source admission')
        require_git_admission(joined_root, manifest, owned_head, source_head)
    _historical_results(root, manifest)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('inputs', 'results'))
    parser.add_argument('root', type=pathlib.Path)
    parser.add_argument('--owned-head', required=True)
    parser.add_argument('--source-head', required=True)
    parser.add_argument('--joined-root', type=pathlib.Path)
    args = parser.parse_args()
    manifest = strict_json(MANIFEST.read_bytes())
    # No caller switch permits the active successor to downgrade to v1.
    if resolve_contract(manifest) != 'diagnostic-v2':
        raise ValueError('Active CLI requires diagnostic-v2')
    if args.mode == 'inputs':
        inputs(args.root, manifest, owned_head=args.owned_head, source_head=args.source_head)
    else:
        results(args.root, manifest, joined_root=args.joined_root,
                owned_head=args.owned_head, source_head=args.source_head)
