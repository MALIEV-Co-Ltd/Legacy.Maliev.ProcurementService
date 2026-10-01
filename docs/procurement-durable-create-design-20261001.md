# Procurement issue27 — durable root-create receipts

## Scope and exact provenance

Base is independently accepted issue26 commit `8d62df486e84d06f0414fe74d32e59bfdad87209`. Protected PR28 merge `031c147c9750c8297af539343d348be537a46bb1` has identical tree `d36f376e5b277b5fbda2e8ca8b369e375dd0c5a4`; root confirmed exact-main CI36790220785 SUCCESS. Owned branch `codex/procurement-durable-create-receipts-20261001`, worktree `B:/maliev-legacy/.worktrees/procurement-runtime-parity-20261001`. Private Defaults `8f4f5f27b226ffe406c4c79b1903742e8c2e7dd3`, Contracts `78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7`; no shared outputs.

The initial gate allowed NEW tests/doc only; root subsequently read complete design/22 cases and authorized the bounded implementation described below. No commits, activation, GitHub, persistent data, source SQL, IAM grants or GCS payload writes. Issue26 doc/archive and all95 original tests remain unchanged. Archived original RED snapshot SHA256 remains `ADE96C73725BAEE64D838A4F35A0F511D1FA1E7DB9972485902840CAF5CBD91B`; its exact method is restored into the new independent fixture/test file. Disposable two PostgreSQL18.1 containers per new class, real Production JWT middleware/RS256, fixture-specific issuer/audience, normal registered repositories/controllers/services. Test-only exact service-grant opt-in for PO positives, never fake IAM or live production capability evidence.

Original controllers and browser create objects last changed at `5fac706a7983a6d359b39acbd670e6800afe020e`, inspected only via committed source mirror checkpoint `bed10c7d15e0698e0b75f1329d0f312937f5d77f`: Supplier profile then address; PurchaseOrder root then children/PDF/upload/link; no idempotency keys/aggregate atomicity. Preserve prior approved current field mapping (including proper SupplierContactPerson), timestamps, DTO/routes/PascalCase/null omission, permissions, both different Address models and external SupplierID/EmployeeID scalars.

Current Intranet `2746d0579568d31a6d12fcbb8358439e33ef5b82`: SupplierCreationClients last change `952ed62cceb9088ee2fcb1b5955c2162f06ad228` generates a new GUID per profile call; PurchaseOrderCreationGateway last change `e204096eb51de31137643e8b465117ee5869493d` forwards stable attemptId to `/PurchaseOrders`, separately derived keys to item/upload/file-link operations and compensates root/children on later failure. All those outbound clients use LegacyServiceAuthenticationHandler and server service-login token. Auth `8cdb634b3b0abdf18b9b826a0948dbfd98c66ea0` signs `sub=service:{clientId}`, rotating jti and identity_kind=service. Actual BFF actor is service:legacy-intranet, NOT browser employee. No browser identity or payload EmployeeId fallback.

This slice guarantees only two root-create operations. It does not make BFF graph workflows atomic, Supplier browser retries stable, PO child writes idempotent, human-owner isolated, GCS replay-safe or Aspire accepted. Permanent root receipts plus BFF compensation/deletion require a separate consumer acceptance gate before activation.

## Approved API, binding and canonical signatures

Local opt-in `Procurement:DurableCreates:Enabled=false` by default; no deployment/configuration enables it. Disposable tests set true. Disabled behavior remains existing legacy create/cache semantics. Enabled with absent key keeps no-key legacy creation; present malformed/empty/multiple/over256 UTF8-byte key returns generic400 before mutation. A single key is exact, case-sensitive, not trimmed; comma/control characters are rejected to prevent coalesced headers. Existing GUID consumers fit; root approved these constraints.

Actor extraction uses authenticated JWT scheme projection only: exactly one nonempty iss and sub, ordinal exact values, issuer matches configured validated issuer, no fallback claims/name/employee/session/browser. Propose issuer<=1024 UTF8 bytes, subject<=512. Existing normal middleware already rejects duplicated JSON sub with401 (characterized), so do not weaken/change middleware merely to force400. Missing/ambiguous actor reaching controller must fail closed, never pick first. Permissions run on every request BEFORE any receipt read/body disclosure; PO retains RequireLiveCheck/IsCritical/default-off service policy. Token renewal/jti change with same issuer/sub preserves actor namespace; token/credentials never persisted/logged.

Proposed Application models and methods:

```csharp
public sealed record CreateReceiptBinding(
    byte[] IssuerDigest, byte[] SubjectDigest, short Operation,
    byte[] KeyDigest, short CanonicalVersion, byte[] PayloadDigest);
public sealed record DurableCreateResponse(
    int EntityId, byte[] Body);
public enum DurableCreateStatus { CreatedOrReplayed, Conflict, Unavailable }
public sealed record DurableCreateResult(DurableCreateStatus Status, DurableCreateResponse? Response = null);
Task<DurableCreateResult> CreateSupplierAsync(
    UpsertSupplierRequest request, CreateReceiptBinding binding,
    Func<SupplierResponse, byte[]> capture, CancellationToken token);
Task<DurableCreateResult> CreatePurchaseOrderAsync(
    UpsertPurchaseOrderRequest request, CreateReceiptBinding binding,
    Func<PurchaseOrderResponse, byte[]> capture, CancellationToken token);
```

API-private binding helper receives authenticated controller projection, actual header values, typed DTO and fixed operation; it cannot accept browser actor fields. SHA256 separately hashes exact UTF8 issuer, subject, key. Operations fixed1=SupplierCreate and2=PurchaseOrderCreate; jti/token/audience/EmployeeId do not define actor. Payload version1 serializes ALL current sealed record properties in declared constructor order, PascalCase, including null, using local canonical JSON options. Supplier eight fields; PO seventeen fields, nullable integers as integers. Exact ordinal strings including whitespace/empty, no trimming/case/Unicode normalization not performed by existing create mapper. Omitted optional fields and explicit null bind identically; null/empty differ. Effective DTO binding determines semantics, not raw JSON property order/casing or ignored extras. Never persist raw key/request/JWT. Payload fingerprint includes fixed operation/version bytes; no generated ID or server date. Future DTO/canonicalizer changes require explicit canonical-version compatibility review rather than silently changing version1.

Same issuer/sub/operation/key+same fingerprint replays exact201 bytes and named route/ID. Same namespace/key with different fingerprint -> generic409, no mutation/disclosure of prior payload. Different actor or operation is a different namespace, not a cross-actor replay. Auth denied -> existing401/403, even if a matching receipt exists.

## Proposed per-database additive schema

`SupplierCreateReceipt` exists only in Supplier DB; `PurchaseOrderCreateReceipt` only in PO DB. No coordinator DB/cross-DB FK/transaction, Address alteration or shared contracts. Proposed immutable columns:

|Column|Type/invariant|
|---|---|
|IssuerDigest, SubjectDigest, KeyDigest|bytea NOT NULL, each octet_length=32|
|Operation|smallint NOT NULL, check1 for Supplier table/2 for PO|
|CanonicalVersion, ResponseVersion|smallint NOT NULL, check=1|
|PayloadDigest|bytea NOT NULL, octet_length=32|
|EntityId|integer NOT NULL, check>0, no cascading entity FK|
|ResponseBody|bytea NOT NULL, nonempty immutable exact legacy JSON snapshot|
|ResponseDigest|bytea NOT NULL, octet_length=32, SHA256 of exact persisted response bytes|
|CreatedAtUtc|timestamp with time zone NOT NULL, effect receipt creation time|

Named composite primary/unique constraint on IssuerDigest+SubjectDigest+Operation+KeyDigest (exact constraint name inspected for arbitration), supporting point lookup. Complete receipts only; no committed Pending row or nullable completion fields. Response201/content-type/application-json and route name are fixed by table/version rather than arbitrary persisted HTTP headers/absoluteHost. Body contains the same supplier/PO response PII already stored in owning DB; do not log it. Capture exact PascalCase/null-omitted bytes before commit and return those same bytes first/replay, avoiding DateTime precision/later updates changing historical response. No new arbitrary Note/Notes size restriction: existing DTO/text fields are unbounded; any operational cap must follow verified existing HTTP admission limits and receive explicit compatibility approval.

No TTL/pruning/key reuse or receipt cascade on entity deletion. Historical replay returns original201/ID, not recreated entity; do not assert current entity existence. Root-delete/compensation consumer consequences remain separate. Existing Redis responses cannot be trusted/backfilled because they lack actor/fingerprint; enabled durable requests ignore them as authority.

## Transaction, cancellation and teardown invariants

Fresh owning-DB context from exact configured options per strategy attempt. Probe matching receipt first. If absent, one transaction inserts root and complete response receipt, then COMMIT. Named receipt uniqueness arbitrates concurrent same-key roots: losing transaction rolls back its root, then fresh-read winner returns exact snapshot or409. Temporary rolled-back generated IDs/sequence gaps are acceptable; no second durable root/orphan. Only exact receipt unique violations trigger this path, not FK or unrelated constraints.

Retry only demonstrably precommit and confirmed rolled-back transient attempt, with new context and fresh probe. Rollback failure or disposal overriding unconfirmed rollback must be typed nontransient503, never replay. Once COMMIT submitted, an exception including transaction/context teardown must not escape as retryable. Fresh bounded independent receipt probe may prove matching committed result; absent/unavailable does NOT prove rollback -> generic503/no internal recreation. A later authenticated caller retry safely arbitrates any still-in-flight earlier transaction through uniqueness. Never generic retry around whole two-DB workflow.

Cancellation before write/commit rolls back, no receipt/effect. Caller abort propagates cancellation, not infrastructure reclassification or fabricated success. Known normally returned commit retains effect/receipt; canceled response can be retried with same key. Cleanup/probe uses separate bounded internal token where required; must not consume caller data/authorize unrelated actor/background mutation. Corrupt/unrecognized stored snapshot/schema is503, no unsafe create fallback.

## Readiness/rollout and remaining proof gate

Enabled keyed creates require read-only physical readiness of owning table/column types/nullability, digest/check invariants and exact uniqueness, not only migration history. Both owning DB states checked independently; no startup/persistent DDL. Missing/drifted schema=>generic503/no mutation. Additive migrations/readiness first, old writer drain and old-key outstanding attempt reconciliation before enabling, consumer acceptance afterward. Guarantees start at coordinated cutover; old acknowledged cache entries cannot be retroactively actor/payload bound. Rollback to unsafe writer/flag-off after activation needs drain/reconciliation, not silent fallback. Production activation not authorized.

The original design-only schema tests demonstrated missing receipt tables. Current disposable migrations and real HTTP tests cover missing table/check/PK, nullable column, RLS/forcedRLS, default, unexpected trigger/unvalidated FK/generated column and deferrable PK. Physical readiness examines exact required columns/types/nullability/no generated/default/identity metadata, exact validated nondeferrable checks/PK, valid ready immediate unique primary index, and rejects table rules/RLS/triggers. PostgreSQL18 native NOT NULL catalog constraints are accepted only with required-column metadata and validated/nondeferrable state. No startup DDL. Both migration Down methods throw before any destructive operation; real disposable IMigrator downgrade tests retain migration history, root and complete receipt. No silent deletion/pruning/unsafe rollback fallback.

Historical preimplementation checklist, not a claim of executed acceptance: exact receipt bytes/rows and no payload/key/token leakage; cache outage/recovery; cross-host same/different payload arbitration; same service actor different EmployeeId payload conflict; operation/issuer isolation; renewed JWT and denied replay; missing/malformed actor/key; corrupt receipt503; lost COMMIT acknowledgement and real context disposal; precommit/caller cancellation/rollback-disposal faults; late in-flight commit with absent probe; entity deletion no resurrection; readiness physical drift/default-off unchanged; root BFF compensation/retry limitations documented. The implemented-case evidence below supersedes this prospective list; unmodeled items remain explicit rather than being implied passing. No mocks/fake authentication as acceptance.

## Evidence chronology and allowed ownership

Baseline Release0W0E3.47s, unfiltered95pass0fail0skip15s, `TestResults/procurement-issue27-baseline-full/natth_MALIEV-31USFIV_2026-10-01_06_15_38_net10.0.trx`. First new13cases Release0W0E2.86s:10genuine failures/3pass, `procurement-issue27-contract-red/...06_18_04_net10.0.trx`: both cacheloss/concurrent/actor/payload defects and null-v-empty conflict; current-permission2 and null-v-omitted1 controls pass. Expanded22 diagnostic Release0W0E2.85s:17fail/5pass `procurement-issue27-complete-contract-red/...06_19_59_net10.0.trx`. One diagnostic failure was an over-specific new assertion400 for duplicate sub; actual normal JWT middleware correctly401, so classified as existing secure behavior and corrected to401 without runtime/auth repair. Other16 are genuine missing durable/header/schema behavior. Final corrected focused/full/static evidence follows before root gate.

Initial allowed writes were only `Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs` (includes new independent fixture) and this doc. Root later approved API-private actor/key/fingerprint/snapshot helpers/readiness registration, the two create controller methods; narrow Application receipt result/interfaces; ownData receipt entities/configuration/migrations/transactional create; new tests only. No old issue26 doc/archive/assertions, Address/child runtime, shared Defaults/Contracts, global IAM/auth, consumer UI/GCS, ledger or CI changes. Entireowner/18ledger completion is not claimed.

All builds/tests use exact absolute `-p:UseLocalMalievDependencies=true -p:MalievWorkspaceRoot=B:/maliev-legacy/.worktrees/procurement-runtime-parity-20261001/.dependencies`. No commits/push. Main-tree equality verified after terminal; branch base remains accepted identical tree until root-approved integration/rebase.

Final corrected new22 Release0W0E2.48s:16 genuineRED/6pass/0skip, `TestResults/procurement-issue27-final-contract-red/natth_MALIEV-31USFIV_2026-10-01_06_23_02_net10.0.trx`. Unfiltered117:101pass/16fail/0skip16s, `TestResults/procurement-issue27-design-full-red/natth_MALIEV-31USFIV_2026-10-01_06_23_15_net10.0.trx`; all original95 pass unchanged. Six controls: current permission on replay2, omitted/null equivalence, duplicate sub401, wrong signed issuer401, default-off PO service403. Failures: archived Supplier cachelost key1, exact cacheloss replay2, actor isolation2, independenthost concurrent root2, payload conflict2, null/empty conflict1, invalid header4, proposed independent receipt schema absence2. Whole format verification0. This is an intentional TEST/DESIGN RED handoff, not a validated runtime slice or completed issue27; no exclusions/skip/old test weakening.

## Implemented bounded candidate and final evidence

Root approved the initial22-case RED/design and subsequently the additional physical-readiness/rollback repair after actual16-case RED (12fail/4pass/0skip). The12 failures were both databases accepting RLS, forcedRLS, defaults, triggers and unvalidated extraFKs, plus both destructive Down paths. Extra generated-column and deferrable-PK controls already rejected correctly. Retained evidence: `TestResults/procurement-issue27-readiness-down-red/natth_MALIEV-31USFIV_2026-10-01_08_51_46_net10.0.trx`.

The first stricter guard diagnostic (41fail/23pass) counted PostgreSQL18's native NOT NULL constraints as unexpected; repaired only catalog classification, retaining validation and required-column metadata. Confirmed64/64 passed at `procurement-issue27-readiness-green-confirmed/...08_54_16_net10.0.trx`. Additional exact UTF8/case/malformed key, disabled/absent-key and committed-but-unavailable-proof controls yielded80/80, followed by four actual caller-abort controls after commit/during fresh receipt query yielding84/84. Caller abort propagates; already committed root/receipt remain, and subsequent retry returns original proof without another root. Tests use actual normal HTTP, normal RS256 middleware, registered configured retry strategy and two independently disposable PG18 databases. Only test interceptors schedule deterministic faults/barriers; they do not provide authentication or replace repositories.

The implementation's receipt body checksum detects accidental persisted-body corruption; it is not keyed integrity against a privileged database editor. Immutability is enforced by this application's insert-only receipt path, no entity cascade and refusal of destructive migration Down. No claim of new database privilege policy or protection against privileged external writers. Existing old writers must be drained; unrelated schema changes require coordinated maintenance, not concurrent DDL against active receipts. This slice adds no startup DDL, backfill, TTL, pruning, persistent schema activation or production rollout.

Final serial commands (owned worktree, private properties on every build/test):

```powershell
dotnet build Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj -c Release -p:UseLocalMalievDependencies=true -p:MalievWorkspaceRoot=B:/maliev-legacy/.worktrees/procurement-runtime-parity-20261001/.dependencies
dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj -c Release --no-build -p:UseLocalMalievDependencies=true -p:MalievWorkspaceRoot=B:/maliev-legacy/.worktrees/procurement-runtime-parity-20261001/.dependencies --filter FullyQualifiedName~ProcurementDurableCreateTests --logger trx --results-directory TestResults/procurement-issue27-final-focus
dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj -c Release --no-build -p:UseLocalMalievDependencies=true -p:MalievWorkspaceRoot=B:/maliev-legacy/.worktrees/procurement-runtime-parity-20261001/.dependencies --collect:"XPlat Code Coverage" --logger trx --results-directory TestResults/procurement-issue27-final-full
```

Release0warnings/0errors3.80s; final focus84pass/0fail/0skip10s; unfiltered179pass/0fail/0skip21s, including original95 unchanged. TRXs `TestResults/procurement-issue27-final-focus/natth_MALIEV-31USFIV_2026-10-01_09_01_29_net10.0.trx` and `TestResults/procurement-issue27-final-full/natth_MALIEV-31USFIV_2026-10-01_09_01_43_net10.0.trx`. Unexcluded coverage `TestResults/procurement-issue27-final-full/f44cce4e-c56b-49c2-85a2-2d297c813cc2/coverage.cobertura.xml`: API29.63%, Application65.85%, Data96.23%, Domain92.20%; API/Application remain below80%, not waived or hidden. No coverage exclusions or skip mechanisms were added.

Whole `dotnet format Legacy.Maliev.ProcurementService.slnx --verify-no-changes --no-restore` exit0 after formatting only new owned C# files. `dotnet list Legacy.Maliev.ProcurementService.slnx package --vulnerable --include-transitive` exit0/no vulnerable packages in five owned projects. Both use environment `UseLocalMalievDependencies=true` and exact absolute `MalievWorkspaceRoot` above. `git diff --check` exit0. Gitleaks stdin scans all12 new file contents and tracked diff: no leaks (`TestResults/procurement-issue27-new-source-gitleaks.json`, `procurement-issue27-tracked-diff-gitleaks.json`). Both private clones remain clean at exact pins; archive hash remains unchanged.

Both owning migrations' `has-pending-model-changes --configuration Release --no-build` checks exit0/no pending model changes, using own Data design-time factories and nonconnecting dummy localhost:1 design-only configuration. Existing EF CLI10.0.5 reports its version is older than runtime10.0.12; no tool/package version was changed. Additive migrations create only the independent receipt table/PK/checks, preserving old entities and both incompatible Address schemas. Down throws before emitting destructive operations, independently tested against each disposable migrated DB. Migration audit: no destructive Up, no entity FK/cascade, exact point-lookup composite PK present, no custom xmin; destructive rollback blocked. These are code/disposable acceptance checks, not promotion authorization.

Excluded diagnostics retained rather than claimed green: one missing `.sln` command (actual solution is `.slnx`); build-time missing EF infrastructure namespace and EF1002 fixture SQL diagnostics (no tests after failed build); two fixture-only JSON `ExecuteSqlRaw` formatting exceptions; first generated static-assets cache build failure; stale no-build run following that failed build; and stricter readiness41fail diagnostic above. The two owned all-NUL generated cache files were preserved under `TestResults/issue27-generated-cache-evidence` and rebuilt. No sibling outputs were deleted or consumed. Final acceptance uses only the fresh exact private Release graph and final TRXs above.

Controlled COMMIT tests distinguish actual successful server commit followed by lost acknowledgement/async teardown, attempted commit throwing before wire completion, and postcommit unavailable/canceled proof. They do not pretend to emulate every network packet timing or production distributed failure. Concurrent independent hosts and exact unique constraint arbitration cover durable roots under replay/conflict. No request-level lock is acquired ahead of the controlled root-save barrier. Only proven precommit rollback retries; commit-submitted/rollback-uncertain/teardown outcomes never escape as transient mutation retries. Five-second fresh proof uses exact immutable actor/operation/key/payload and returns503 if unavailable or absent, never treats absence as rollback proof.

### Exact changed-file ownership (18 files)

- API: `Controllers/SuppliersController.cs`, `Controllers/PurchaseOrdersController.cs`, `Program.cs`, new `DurableCreateEndpoint.cs`.
- Application: new `Interfaces/IDurableProcurementCreates.cs`, `Models/DurableCreateModels.cs`.
- Data: `ProcurementDbContexts.cs`; new `CreateReceiptRecord.cs`, `DurableProcurementCreates.cs`, `ReceiptReadiness.cs`.
- Data migrations: Supplier `20261001013648_AddDurableSupplierCreateReceipts.cs`, matching `.Designer.cs`, `SupplierDbContextModelSnapshot.cs`; PurchaseOrder `20261001013651_AddDurablePurchaseOrderCreateReceipts.cs`, matching `.Designer.cs`, `PurchaseOrderDbContextModelSnapshot.cs`.
- Tests: new `Integration/ProcurementDurableCreateTests.cs` only; original95 tests and archived RED unchanged.
- Doc: this file only. No changes to source originals, canonical checkout, dependencies, shared contracts, children/Address runtime, CI, global auth, consumers or ledger.

Production activation, old-writer/key cutover reconciliation, BFF stable Supplier attempts/PO graph compensation, human-authority binding and real cross-service/production-derived Aspire remain separate gates. This passing local candidate is not whole workflow/owner closure. No commits or pushes; parent performs independent acceptance/integration.

### Final parent-requested EmployeeId scalar control

Root review requested one additional meaningful normal HTTP test because the same-service/key changed-EmployeeId case was not independently covered. `PurchaseOrderCreate_SameSignedServiceAndKeyChangedEmployeeId_ConflictsWithoutChangingActorOrEffect` uses the identical signed `service:legacy-intranet` subject and exact key, changing ONLY payload EmployeeId: initial201, conflict409, one root/receipt, original persisted EmployeeId, then byte-identical original replay. This proves EmployeeId is a payload scalar, not an actor namespace or browser/human authority claim. Runtime remains unchanged.

Superseding final Release0warnings/0errors2.41s; focused85pass/0fail/0skip10s; full180pass/0fail/0skip19s including all original95. Exact TRXs: `TestResults/procurement-issue27-employee-scalar-final-focus/natth_MALIEV-31USFIV_2026-10-01_09_06_21_net10.0.trx` and `TestResults/procurement-issue27-employee-scalar-final-full/natth_MALIEV-31USFIV_2026-10-01_09_06_34_net10.0.trx`; latest unexcluded coverage `TestResults/procurement-issue27-employee-scalar-final-full/428116d6-47a7-48fc-afdf-10301c6c6ef3/coverage.cobertura.xml`. Earlier179 results remain passing prior evidence, not the final test tree.

Final post-control whole format verification and five-project transitive vulnerability audit exit0; diff whitespace check0; final Gitleaks new-file/diff scans no leaks (`TestResults/procurement-issue27-final-new-source-gitleaks.json`, `procurement-issue27-final-tracked-diff-gitleaks.json`). Latest coverage remains API29.63%, Application65.85%, Data96.23%, Domain92.20% without exclusions. All build/test/static handles are terminal at writer release. Parent receives exclusive file/output ownership for independent review; no more edits/builds by this lane after release.

Unmodeled/residual proof is not counted green: every possible on-wire late COMMIT timing, privileged DB tampering, independent multi-issuer grants (normal configured issuer rejects mismatches), actual production actor grants, all seventeen fields changed individually, general distributed fencing, whole BFF child/compensation/notification workflow and real Aspire promotion. Effective canonicalizer includes all8/17 current typed fields; the meaningful payload-change tests exercise supplier fields, PO contact/notes and EmployeeId plus null/empty/default equivalence, not invented per-field coverage. All activation controls still default off. API/Application coverage below80 remains an unresolved quality gate, not a raw/generated-code waiver.

### Independent integration review

Root rebuilt the direct Tests project against the exact private dependency pins in Release: zero warnings/errors, including shared dependencies. Focused85 and full180 passed with zero failures/skips; root TRXs are `TestResults/root-procurement-durable-focus` and `TestResults/root-procurement-durable-full`. Whole-solution verify-only formatting and five-project transitive vulnerability audit passed. The initial solution build selected Debug for shared projects; acceptance instead uses the subsequent direct Release graph. Both additive migrations/snapshots preserve existing entities and expose no destructive rollback.

Issue27 was accidentally closed by the preceding PR28; it was reopened because this receipt slice was not yet merged. Broader source-contract, API/Application coverage and Aspire acceptance remain explicitly open in issue29. No raw coverage threshold is waived, and no persistent schema or application is activated by this code review.
