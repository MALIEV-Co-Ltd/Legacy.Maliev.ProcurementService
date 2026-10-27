# Procurement bucket storage boundary: source qualification and missing regression coverage

Candidate base: `8c4eb871da1cdb526ff1951063a829ad77c10dde`, tree `81606e7e1a5686c32f7a86fea959f93b61f2cf50`. Existing issue #55 records this bounded owner obligation; issue #29 and all broader source obligations remain separate.

## Existing implementation and actual gap

The physical constraint is already implemented. PR #40 introduced commit `54613967c554f94a7838c98ebad0fb8145b0a7fe`, parent `1f7b16bfa6d636dcd7ecd9159a9350178c3c5c59`. Current migration `20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs`, blob `1663bacce0bf61de8db5688a82e48354c24ba658`, adds `CK_PurchaseOrderFile_Bucket_UTF16` and validates retained rows. It uses existing 5-second lock and 30-second statement limits in both directions. The model helper `2e68e9f383160dfe6082f7a23b859bfbf5b2d325`, context `1a8487f24a647a186258d487b84e1cc08fa7d83b`, designer `143e1ae02a1fd1100eb2d75dce9b8124188e4cd4` and current snapshot `b3477b7823f63b37bed92959f7100e3cd287baf9` retain the same 50-unit constraint.

Issue #55's statement that the physical bound is absent is stale against these current sources. This packet does not add a second constraint or change any migration/model/runtime file. It fills missing bucket-specific direct-SQL migration tests in the existing source-string migration suite. Existing API/repository bucket tests `4053059853b34e541ea0e9bfc8a4c3178e7ec4d8` cover tracked writes; the existing migration suite `c7817e2409b49f32423230199bda79a5e79609cd` exercises Supplier/PartNumber retained rows, not the file bucket.

## Exact original association

All three relevant original paths were inspected by bounded committed-object reads, without inspecting configuration or credential files:

- `Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/PurchaseOrderContext.cs`
- `Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/PurchaseOrderFile.cs`
- `Maliev.PurchaseOrderService.Api/Controllers/FilesController.cs`

Original initial `5fac706a7983a6d359b39acbd670e6800afe020e` has no parent. The corresponding blobs are `99aa62f40a6478a9dd2243d41730f497b22b1077`, `555d54fc2d025fe25a595664c174a24a5b30fcba`, and `158240d27dd9119b88599c6e7f5294c77d948cfe`.

Original `72eb9f1949176392141951d35e6e06f7c30af4c2`, parent `023aa2f143fa5a8f557d72c1302b9add64792d6a`, retains blobs `af7e4a90d179c36dffe73702831ed4a3b212c800`, `3afd2302961d1efb16564d345b53c7d4991582e1`, and the same controller blob.

Original `2aab25eb07894fc0267b03b85bad96490219d2fa`, parent `56014f2efc7c7f24b777c51d17a454e023d12bdd`, retains blobs `b9932458bc38d83f380b0abb17500109b1fea6e3`, `3afd2302961d1efb16564d345b53c7d4991582e1`, and the same controller blob.

The original Bucket property remains required with HasMaxLength(50) across all three anchors. Narrow property excerpts, not whole initial-source inventory, establish this field contract. Historical SQL Server execution/binary/database provenance is not claimed. Source-owner association does not establish whole-source acceptance. The ledger is unchanged, and this mixed-owner association earns no whole-source closure.

## Authored regression boundary

Ten added cases retain every previous test body and original case:

- Two retained-row cases insert PostgreSQL scalar-valid but source-invalid 51/52 UTF16-unit supplementary buckets before the existing string-boundary migration. Upgrade must refuse with the exact named check constraint and preserve parent/file rows, owned table columns/constraints and applied migration history.
- Six valid literal cases cover empty, whitespace, padded text, BMP length 50, supplementary length 50 and mixed/padded length 50. They verify the physical validated constraint, literal preservation through upgrade/repeat/rollback/re-upgrade, and direct SQL insert/update rejection for null, BMP overflow and both supplementary overflow shapes. Each refusal must leave rows/schema/history unchanged.
- Two contention cases hold an explicit table lock and require the existing upgrade/downgrade lock budget to refuse without altering rows/schema/history. Releasing that owned transaction must permit the same migration direction.

The tests target the original reversible boundary explicitly. Later durable child-receipt migrations are not applied or downgraded. Existing separate Supplier/PurchaseOrder databases, current nullable-address #86, all 30 HTTP actions, DTO/JSON/auth/permission/idempotency semantics and application/repository guards remain unchanged. The added methods use the existing class/container lifecycle and 90-second operation cancellation; no new fixture, helper process or worker framework is introduced.

## Validation and handoff

Author source checks: exact original SHA/parent/path association, current protected-main source/model/migration inspection, strict unique insertion with byte-exact inverse preserving the entire prior test file, immutable postimage readback, nontruncated two-leaf tree delta and actual inverse-tree equality before final handoff. New test rows are authored forecasts, not passing counts.

Release build, focused old/new PostgreSQL migration cases, complete affected suite, formatting, static/security/audit/contract and unchanged coverage gates are **not run** in this source-only lane. Root owns exact-head hosted validation and protected publication/merge; all applicable existing gates remain required. The existing migration has not been applied to any database here. No local SDK/Docker/test host or financial-stopped runtime is executed. No deployment, persistent schema/data, cloud/workload, credential, registry pin, original repository, private ledger or canonical checkout changes occur. Quotation #183 Hub provenance, Comment/TrackingNumber, FX and other owner holds remain intact.
