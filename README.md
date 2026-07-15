# Legacy.Maliev.ProcurementService

Public, sanitized .NET 10 compatibility extraction of the supplier and purchase-order domains
from the private `maliev-web` monorepo. One independently deployable service replaces the two
tightly coupled legacy APIs while preserving their separate data ownership and HTTP contracts.

## Architecture and security boundaries

Dependency direction is `Api -> Application -> Domain`; the two PostgreSQL contexts, Redis
adapter, and repositories live in `Data`. Scalar/OpenAPI, JWT validation, standard middleware,
health endpoints, resilience, and structured logging come from `Maliev.Aspire.ServiceDefaults`.

All 30 actions require authentication and explicit permissions. Supplier and purchase-order
creates accept `Idempotency-Key`; purchase-order and order-item updates accept
`X-Expected-Modified-Date` and return HTTP 409 for a stale value. Idempotency keys are SHA-256
hashed before Redis storage and responses expire after 24 hours.

## Preserved route families

- `/Suppliers[/{supplierId}]` and `/Suppliers?sort=&search=&index=&size=`
- `/suppliers/addresses[/{addressId}]`
- `/suppliers/{supplierId}/addresses[/{addressId}]`
- `/PurchaseOrders[/{purchaseOrderId}]` and `/PurchaseOrders?sort=&search=&index=&size=`
- `/purchaseorders/addresses[/{addressId}]`
- `/purchaseorders/orderitems[/{orderItemId}]`
- `/purchaseorders/{purchaseOrderId}/orderitems`
- `/purchaseorders/files[/{id}]`
- `/purchaseorders/{purchaseOrderId}/files`

PascalCase JSON, null omission, legacy sort names, named routes, and pagination fields remain
compatible. List sizes are bounded to 250 records to protect the existing cluster.

## Preserved databases, GCS, and caching

- PostgreSQL cluster target: `legacy-postgres-procurement` in `maliev-legacy`, after parity gates.
- Database `Supplier`: `Supplier` and `Address` with legacy `Address1`/`Address2` columns.
- Database `PurchaseOrder`: `PurchaseOrder`, `Address`, `OrderItem`, and `PurchaseOrderFile`,
  including legacy column/FK names and database-computed `Subtotal`.
- The schemas remain separate because both own an incompatible table named `Address`.
- `SupplierID` and `EmployeeID` stay scalar external references; no cross-database FK is added.
- File rows contain GCS bucket/object metadata only; object access uses ADC/Workload Identity.
- Redis prefix: `legacy:procurement:`. Authorized entity reads fail open to PostgreSQL and are
  invalidated after writes.

## Deployment gate

Extraction does not deploy. Cutover requires a dedicated `legacy-maliev-procurement` Workload
Identity, `maliev-gitops/3-apps/_legacy-procurement-service`, repeatable SQL Server-to-PostgreSQL
copy and parity artifacts for both databases, rollback evidence, GCS object reconciliation, and
Web/Intranet consumer tests. Source SQL Server remains untouched during extraction.

Everything must use the existing GKE cluster and `maliev-legacy` namespace. No new node pool,
Cloud SQL, or other paid database service is permitted.

## Validate

```powershell
dotnet restore
dotnet build --no-restore
dotnet test --no-build
dotnet format Legacy.Maliev.ProcurementService.slnx --verify-no-changes --no-restore
dotnet list package --vulnerable --include-transitive
gitleaks git . --redact=100 --exit-code 1 --no-banner --no-color
```
