# Procurement dormant publisher validation adoption

## Frozen scope and compatibility

Base: `d8804a6c44fb72d24423606760d89c5f9ed4b37b`, independently verified clean canonical main/live origin with no open PR at preflight. Candidate branch: `codex/procurement-publisher-validation-20261001`.

Only the reusable publisher pin changes from `73dd7304ffe85ec504389fd7664cc39070b9f148` to reviewed producer `503e8846390a597c267d2889b33a9c26863389b3`, with job-local `actions: read`. The publisher's exact minimal permissions are `contents: read`, `actions: read`, `id-token: write`. Workflow-level permissions remain contents/read only; the planned-only deployment gate has no OIDC permission. Both existing `LEGACY_DEPLOY_ENABLED` conditions remain unchanged.

The complete committed `on.workflow_call.inputs` definitions at the old and new Workflows pins were compared ordinally and are identical: ten names, descriptions, required flags, string types and defaults. Required image/dockerfile/context/environment/WIF/service-account inputs have no new defaults. The four optional dependency refs retain empty-string defaults. Procurement still passes exactly its existing eight inputs. Its private dependencies remain ServiceDefaults `8f4f5f27b226ffe406c4c79b1903742e8c2e7dd3` and CompatibilityContracts `78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7`; absent modern dependency refs remain absent. Dockerfile, context, runtime, configuration and build-test workflow are untouched.

The reviewed producer validates the exact caller main SHA's protected CI result before immutable image publication. This is dormant configuration adoption, not local execution of the publisher or deployment acceptance. No registry, WIF, GitOps, infrastructure or runtime promotion was exercised.

## Individual source traceability

Committed source mirror only: `B:/maliev-legacy/.artifacts/source-commit-mirror-20260930.git`, frozen cutoff `bed10c7d15e0698e0b75f1329d0f312937f5d77f`. Originals were not modified or fetched.

| Full source commit | Procurement-owned committed paths | Source behavior and bounded disposition |
| --- | --- | --- |
| `00ec830615c15b5e4e227046712247b11df0100f` | `Maliev.PurchaseOrderService.Api/deploy.ps1`, `Maliev.SupplierService.Api/deploy.ps1` | Native failure checks and finally cleanup. Reviewed reusable workflow provides failure-propagating immutable publication instead of porting imperative cloud deployment scripts. |
| `72163e9ae11f39f6579423841a2e20529b986fab` | Both preceding `deploy.ps1` paths and their `deploy-service.ps1` wrappers | Explicit success/failure process exit status, wrapper kubectl exit propagation; no ambient stderr/error-collection success inference. Publisher adoption addresses the image-publication boundary only, not kubectl apply. |
| `f8921b1b1d5846eeaff999af10b640011655d1d4` | Both preceding `deploy.ps1` paths | Throwaway version-rendered manifest, missing-placeholder refusal, finally cleanup without modifying source template. No mutable manifest port; immutable image publication does not establish downstream GitOps deployment parity. |

These are individual Procurement boundary assessments, not blanket closure of the shared source commits, other service owners or deployment gates.

## Executed validation

Commands ran sequentially in the owned worktree, using ignored clean detached private dependency clones at the exact refs above. Set `UseLocalMalievDependencies=true` and `MalievWorkspaceRoot=<owned-worktree>/.dependencies` for dotnet commands.

- Initial Release build: zero warnings/errors. Test-first focused RED: 22 passed, 2 failed, zero skipped. Failures specifically assert old reusable pin and missing actions/read. Preserved TRX: `TestResults/procurement-publisher-red/natth_MALIEV-31USFIV_2026-10-01_14_13_46_net10.0.trx`.
- After minimal YAML repair, scoped formatting followed by `dotnet build Legacy.Maliev.ProcurementService.slnx -c Release -p:UseLocalMalievDependencies=true -p:MalievWorkspaceRoot=$env:MalievWorkspaceRoot -nodeReuse:false`: zero warnings/errors.
- `dotnet test Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj -c Release --no-build --no-restore --filter 'FullyQualifiedName~PublishWorkflowPermissionContractTests|FullyQualifiedName~WorkflowContractTests' --logger trx --results-directory TestResults/procurement-publisher-focus`: 24 passed, zero failed/skipped. TRX `natth_MALIEV-31USFIV_2026-10-01_14_16_30_net10.0.trx`.
- `dotnet test Legacy.Maliev.ProcurementService.slnx -c Release --no-build --no-restore --logger trx --results-directory TestResults/procurement-publisher-full`: 189 passed, zero failed/skipped. TRX `natth_MALIEV-31USFIV_2026-10-01_14_16_32_net10.0.trx`.
- Whole solution `dotnet format ... --verify-no-changes --no-restore`, whole-repository `actionlint` (v1.7.12), and `git diff --check`: passed.
- `dotnet list Legacy.Maliev.ProcurementService.slnx package --vulnerable --include-transitive --no-restore`: no vulnerable packages in all five projects against current NuGet sources.
- `gitleaks git . --redact --no-banner`: 36 committed revisions scanned, no leaks. Final owned-file stdin scan and exact CI-pinned signing-resource scanner: passed, no findings.

Parsed tests prove exact pin, exact three job permissions, unchanged gate and eight inputs, and seven mutation controls reject absent, elevated or additional permissions after validating a positive baseline. Existing controls remain intact. No coverage threshold, production endpoint or deployment acceptance is claimed from these workflow tests.

Candidate is reserved for root's independent review/validation. No commit, push or external mutation was performed.

## Independent integration acceptance

Bounded issue31 owns this caller adoption. Root reviewed the complete three-file
diff and repository boundaries. Independent test-project graph Release build had
zero warnings/errors, with all private dependencies also Release; focused24 and
full189 passed without skips. TRXs are in `TestResults/root-publisher-focus` and
`TestResults/root-publisher-full`. Whole formatting, actionlint and whitespace
checks passed. Protected PR and exact-main acceptance remain required; no parent
or whole source-owner closure follows from this caller-only slice.
