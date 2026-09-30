# Procurement startup, privacy and artifact acceptance

Owner issue: [ProcurementService #24](https://github.com/MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService/issues/24), Project 2.
Both original `Maliev.SupplierService.Api` and `Maliev.PurchaseOrderService.Api`
map to this service; their separate database contexts remain separate.

| Full source SHA | Owner paths and concrete acceptance |
| --- | --- |
| `5ac7d045c51194edd9e64d8564f1b726b001be34` | Both Program/Startup/project/Docker paths: actual Production host registers native console/OTel providers, UTC/scopes/trace/Cloud severity and safe correlated failures; built runtime contains no NativeLogging. |
| `9e51e6c5da29de8e617b65b59d46882cde6d3b64` | Both Program/Startup/ServiceExtensions/project/Docker paths: runtime dependency graph and actual Docker publish contain no NLog or LoggerService; safe shared native logging remains. |
| `03dc9a1271c16e6535934445e9dd6e3f30e8fffe` | Both API projects and source XML removals: parse XML next to the actual built API assembly, verify assembly/member metadata and absence at project root; verify published XML inside actual image. Existing GenerateDocumentationFile already implements behavior; no invented project edits. |
| `03eaff1194c3ae2a54ceefeae31deffaff90436f` | Both service-local .dockerignore files: root-context nested exclusion repair plus a real Docker COPY canary build that excludes private/generated artifacts while retaining dependency .cs/.csproj/.props inputs; actual application Docker build proves retained inputs. |

Existing migrated `f0640fe0719b2eb6becda378bff08153d955be07` (both Startup handlers)
keeps issue20/PR21/main `f9084920af54c8c8bb765fb7d55869f8ced733b8` and
CI36393820622 provenance. This bundle strengthens its actual host/controller,
started-response, correlated-event, and real database-failure acceptance.
It does not claim cross-owner source completion.

## Demonstrated missing behavior

Before changing Program, all four real Production-host PostgreSQL read/save
privacy regressions failed: EF query/save diagnostics rendered provider details
and stacks in Message, despite a safe client body and safe middleware event.
Both contexts now suppress only duplicate exception-rendering
QueryIterationFailed, SaveChangesFailed, and ExecutionStrategyRetrying diagnostics.
Other logging and the actionable UnhandledRequestFailure critical event remain.
The approved shared formatter/OTel architecture is retained, not replaced with
the source's provider clearing and unredacted exception serialization.

Before changing .dockerignore, the actual Docker context canary build failed.
The repaired root ignore excludes nested Git/editor/build/test/coverage output,
environment/key files, logs/temp/packages, scripts and manifests, while retaining
source and required .dependencies build inputs. No private source history or
configuration is copied into target history or runtime image.

## Executed checks, 2026-09-30

Set MalievWorkspaceRoot to the isolated worktree .dependencies directory with
exact CI pins: ServiceDefaults `8f4f5f27b226ffe406c4c79b1903742e8c2e7dd3`,
CompatibilityContracts `78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7`.

- `dotnet build Legacy.Maliev.ProcurementService.slnx -c Release`: 0 warnings/errors.
- `dotnet test Legacy.Maliev.ProcurementService.Tests -c Release --no-build --filter FullyQualifiedName~ProductionDatabaseFailure`: pre-fix 4 failures, reproducing actual provider-message leakage.
- `dotnet test Legacy.Maliev.ProcurementService.Tests -c Release --no-build --filter FullyQualifiedName~DockerContextPrivacyTests`: pre-fix 1 failed actual context build.
- `dotnet test Legacy.Maliev.ProcurementService.Tests -c Release --no-build --filter FullyQualifiedName~Startup`: final 11 passed, 0 failed/skipped.
- `dotnet test Legacy.Maliev.ProcurementService.Tests -c Release --no-build --collect:'XPlat Code Coverage'`: 65 passed, 0 failed/skipped, including existing route, migration, concurrency, idempotency and cache tests.
- `dotnet format Legacy.Maliev.ProcurementService.slnx --verify-no-changes --no-restore`: exit 0.
- `dotnet list package --vulnerable --include-transitive`: no vulnerable packages across all five projects.
- `gitleaks dir . --redact=100 --exit-code 1 --no-banner --no-color`: no leaks.
- `Invoke-JwtSigningResourceScan.ps1 -RepositoryPath .`: exit 0.
- `git diff --check`: passed.
- `docker build -f Legacy.Maliev.ProcurementService.Api/Dockerfile -t legacy-procurement-startup-acceptance:20260930 .`: actual application image built.
- `pwsh -NoProfile -File docs/Invoke-StartupArtifactProof.ps1`: passed; script supplies reproducible runtime proof without printing token/key/connection material.

Eleven acceptance cases use actual Production startup and RS256 validation,
real protected Supplier/PurchaseOrder reads with bounded IAM denial, generic500
with null details, service/method/template/status/type/incident/UTC event fields,
W3C and correlation scopes, no literal IDs/query/header/token/provider details,
live-check mutation denial, PascalCase/null omission, started202 preservation,
type-only cache warning/fallback, runtime dependencies/XML and actual Docker COPY.
Two shared disposable PostgreSQL18 fixtures intentionally lack schemas; attempted
writes fail without application persistence. Test-only save/started endpoints are
loaded solely by the factory and are absent from production startup/artifact.

Docker runtime proof: UID1654; liveness200; both actual business routes anonymous401
and authenticated500 against two isolated disposable PostgreSQL containers; matching
critical incidents and no provider-message/stack/literal-path-ID/token leaks. Native
dependency and published XML checks pass. Containers and network are removed.

## Scope and residuals

No route, DTO, permission, idempotency, cache, database schema or consumer changes;
30 approved actions and separate incompatible Address models are preserved.
No SQL Server, production connection, application deployment, image publication,
shared Defaults/Workflows edits or migration against persistent storage.
This is not arbitrary-message redaction for all categories or live OTLP-export
validation. Existing whole-project coverage remains below the 80% skill goal
(API11.85%, Application42.04%, Data93.89%, Domain92.20%); collected, not claimed
passing or expanded into unrelated coverage work. Root owns merge/exact-main CI
and owner-specific ledger updates after PR validation.
