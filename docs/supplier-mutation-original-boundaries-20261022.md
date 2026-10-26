# Supplier mutation source boundaries

## Proven source gap

Retained original initial commit `5fac706a7983a6d359b39acbd670e6800afe020e` has no parents.

| Original path | Blob | Exact behavior |
| --- | --- | --- |
| `Maliev.SupplierService.Api/Controllers/SuppliersController.cs` | `bc52a62384e725e287d1d998ac7f9454d0227791` | Create at line 51 and update at line 204 return empty BadRequest before constructing or finding a supplier when the request is null. |
| `Maliev.SupplierService.Api/Controllers/AddressesController.cs` | `bf906759e57eec2f306bcfd02b9c839760417eb9` | Create at line 54 returns `NotFound("Supplier does not exist")` at line 64 when the parent lookup fails. |

The bounded retained histories for these two paths contain only the initial commit. This establishes these three behaviors, not latest-checkpoint parity, whole-source closure or observed original-host HTTP output.

Current base `0298a8547653b9a13f60509cb9ea9c239c882c33`, tree `6e889149284ba3226dab97d8f7bf893917de5034`, omits the two supplier null guards and maps missing-parent address creation to an empty NotFound.

## Change and boundaries

- Reject null supplier creation before either the optional durable adapter or idempotency/application dispatch.
- Reject null supplier updates before application dispatch, preserving null-before-missing-ID precedence.
- Preserve the exact original missing-parent string in supplier-address creation.

Routes, action signatures, permissions/live-check flags, DTOs/JSON converters, all non-null supplier writes, successful address response and Location, lookup/search/order, transaction/lock/retry behavior and exception handling stay unchanged. Service and repository interfaces and implementations remain unchanged. This slice does not change or enable a durable-create feature, purchase-order or financial behavior, database schema, provider, data migration or deployment. Procurement issue #55 and its accepted file guards are outside this packet; Comment/TrackingNumber and financial/provider holds remain blocked.

The null guards are a callable-controller behavior restoration. Existing ApiController binding may already reject HTTP JSON null; there is no observed HTTP-500 claim.

## Regression coverage and acceptance

New `ProcurementSupplierMutationSourceTests` has eight strict-mock cases: create-null with absent/present key, update-null for IDs 101/int.MaxValue, exact missing-parent response for those IDs, and preserved non-null update delegation for found/not-found. Null cases permit no application or idempotency calls. Missing-parent and non-null controls verify exact request identity, cancellation token, one application call and unchanged result mapping.

New `ProcurementSupplierMissingParentHttpTests` has two normal Program/signed-JWT/PostgreSQL cases for text/plain and application/json negotiation. Both require 404, exact original string value, matching media type, no Location and fresh no-row database readback. They use the existing runtime fixture with its default-off purchase-order boundary and make only a supplier-address request. No authority middleware, application service or repository is substituted by these new tests. The existing fixture supplies its established test cache/clock/configuration. Existing fixture cleanup qualification (#57) remains separate and unchanged.

Both new test files are discovered by the existing SDK test project and ordinary unfiltered full-suite validation. Six existing causal preparers and the Auth join admit only the two exact current controller successors after the frozen address transition; historical graphs, runtime manifest inventories, baselines and native cohort counts remain unchanged. Four closed compiled-source sets enroll the two exact new test paths, verifying candidate working/HEAD hashes and absence in frozen baseline objects and working trees. The corresponding four contracts advance only consumed script bindings. Shared negative controls are imported by the seven workflow-selected control modules. No workflow, native result roster, dependency or coverage threshold changes are needed. The two classes can be selected with:
`FullyQualifiedName~ProcurementSupplierMutationSourceTests|FullyQualifiedName~ProcurementSupplierMissingParentHttpTests`.

Author verification is source-only: bounded original SHA/parent/path/blob reads, exact reversible literals and immutable readback/tree checks. Six new shared Python control methods cover exact transition/non-mutation, malformed or already-advanced preimages, old/missing/unknown runtime rejection, actual Auth exact-input joins, working/HEAD test binding and frozen-baseline absence, and every preparer integration. All normal and optimized Python controls are not run author-side and require hosted execution. Release build, ten new cases, focused/full suites, format, static/security, boundary execution and raw coverage are **not run author-side**. Heavy validation stays on GitHub Actions under Root's existing authority and unchanged admission/gates. Root must obtain passing exact-head checks and protected-main verification before acceptance; existing financial-stopped execution restrictions remain in force.

No native SDK/test host, container, database, cloud, official-log retrieval or ref operation was performed by the author. No helper resources were allocated.
