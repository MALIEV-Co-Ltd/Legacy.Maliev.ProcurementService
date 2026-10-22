# Supplier address parent audit timestamps

## Retained source and current gap

Original initial commit `5fac706a7983a6d359b39acbd670e6800afe020e`, parents `[]`, owns `Maliev.SupplierService.Api/Controllers/AddressesController.cs`, blob `bf906759e57eec2f306bcfd02b9c839760417eb9`. CreateSupplierAddressAsync starts at line 54, sets the new address's CreatedDate and ModifiedDate at lines 74-75, and changes only supplier.AddressId before saving at lines 83-84. DeleteSupplierAddressAsync starts at line 102 and clears supplier.AddressId, removes the address and saves at lines 111-113. Neither path assigns Supplier.ModifiedDate. Address PUT changes the child's ModifiedDate only.

The bounded retained controller history contains only the initial commit; its blob is identical at `72eb9f1949176392141951d35e6e06f7c30af4c2`. The initial Supplier model blob is `889f0ddf257f19dfde25648fba74690e63ca3f95`; retained EF context blob `dffa8ac48b53556f3ee20c805a0463c7ef7ce776` defines nullable datetime audit properties with insert defaults, and no update-generation configuration. This describes retained C#/EF source, not live SQL Server trigger state or a latest-checkpoint audit.

Protected source preimage `0298a8547653b9a13f60509cb9ea9c239c882c33`, tree `6e889149284ba3226dab97d8f7bf893917de5034`, has repository blob `f116b6f1f0258f2f3bfd0eb35190bd14a64c06f4`. SupplierRepository.CreateAddressAsync and DeleteAddressAsync additionally overwrite the parent's ModifiedDate. This changes subsequent supplier reads and modified-date ordering even though the caller changed an address.

The complete packet layers onto Root's separate Supplier mutation PR89 head `696bcb8966e5861f6115fae55748bc1287f714fd`, tree `425c468b9fbe48a3c95261dc6e8b83a1482a1d02`. That head retains the exact same repository preimage. The parent audit slice is a distinct logical successor; it does not duplicate or replace the Supplier mutation slice.

## Bounded implementation

Remove only these two parent timestamp assignments. Keep address timestamps, pointer replacement and owned delete semantics, the parent row lock, transaction/retry/uncertain-commit handling and cache invalidation unchanged. No model, DTO, query, schema, permissions, receipt, financial, provider or deployment changes are included.

The controller/service path delegates Supplier address creation/deletion to SupplierRepository. Application service source blob `28204fc1402f836d1da3ae94542bb5ce249b1c1b` invalidates the existing supplier cache after success; reads query the repository. Supplier address operations do not use the purchase-order child durable receipt implementation. The existing Supplier controller/null and missing-parent packet is separate and unaffected.

## Regressions and hosted gate

New SupplierAddressParentAuditSourceHttpTests has eight rows: four attach/replace cases, two delete cases and two address-PUT controls, each covering null or existing parent ModifiedDate. Each uses normal Program/controller/service/repository behavior with the existing ProcurementRuntimeFixture. Fresh SupplierDbContext readback and HTTP PascalCase/null-omission assertions require unchanged parent CreatedDate/ModifiedDate; child dates and literal updates, replacement retention, pointer detach, no orphan on delete and empty PurchaseOrder-owned tables are also checked.

The fixture uses two PostgreSQL18.1-bookworm containers, a signed RS256 token, an existing deterministic fake clock and the existing in-memory distributed-cache fixture. It does not constitute live Redis/IAM acceptance. Nullable parent ModifiedDate is explicitly written after insertion so the schema's insert default cannot silently defeat the null case. Fixture isolation/reset and normal cleanup are retained. The existing controlled transaction/lost-acknowledgement/lock/cancellation tests remain unchanged.

The new bounded GitHub Actions workflow selects all eight new rows plus the existing nine transaction-boundary cases, using the existing immutable dependency/action pins, contents-read permissions and retained TRX/coverage evidence. Six causal preparers and the Auth input checker apply a strict current-consumer repository successor, and exact test admission is added separately from each frozen compiled roster. The shared helper preserves its complete preceding implementation. Nine new Python rejection controls are imported by all seven workflow-selected control modules; three synthetic current-runtime maps use the new exact transformation. Four contract files advance only their consumed scriptBindings (four existing hashes and one new source binding each); every other field remains equal. The preceding shared address controls retain their pure transition tests and update only the integration assertions to require the outer parent-audit transformation and its exact validator functions. All historical runtime graphs, source hashes, sealed baselines, execution rosters, thresholds, count parsers and image acquisition policy stay unchanged. A baseline prediction is six failures at unchanged-parent assertions and two PUT passes; no RED run has been executed author-side.

## Acceptance and holds

Author checks: exact retained SHA/parents/path/blob/line provenance; current producers/consumers, nullable timestamp/default mappings, fixture and normal transaction path; unique reversible two-hunk patch; immutable post/pre readback and exact tree/inverse proof. Source review and tree evidence are recorded in the handoff manifest.

Release build with zero warnings/errors, new eight cases, focused17/full suite, formatting, static/security, boundary behavior and raw coverage are NOT RUN author-side. Root owns exact-head GitHub Actions execution, official logs and protected-main acceptance. Existing provider-image preflight failures remain unresolved; no bypass or waiver is included.

Comment/TrackingNumber, all financial/provider/status-transition execution, recursive financial graph, GCS/cloud/data/deployment/ancestry/security holds remain. No source checkout, tracking ledger, refs, commits, publication, native test host, worker or container was created or changed by the author. No task-owned resources remain. This bounded slice grants no whole-source or latest-checkpoint closure credit.
