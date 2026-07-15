# Legacy.Maliev.ProcurementService agent guidance

## Boundaries

- Preserve all 30 approved supplier, supplier-address, purchase-order, purchase-order-address,
  order-item, and file-metadata actions, including route/query names, sort values, named routes,
  PascalCase JSON, and null omission.
- Keep the incompatible legacy `Address` tables isolated: `SupplierDbContext` owns Supplier's
  `Address1`/`Address2` schema, while `PurchaseOrderDbContext` owns the
  `AddressLine1`/`AddressLine2` schema. Never merge these databases or introduce cross-database FKs.
- `SupplierID` and `EmployeeID` are external scalar references. Catalog/material and employee
  records belong to their own services.
- Store Google Cloud Storage bucket/object metadata only. Runtime access uses ADC/Workload
  Identity; never add service-account files, access keys, signed URLs, or credentials.
- Do not alter source SQL Server or deploy during extraction. PostgreSQL promotion requires
  artifact-backed parity, rollback, and consumer gates.

## Runtime constraints

- .NET 10, Scalar/OpenAPI, Npgsql, Redis, built-in `ILogger<T>`, and standard MALIEV service
  defaults are required.
- Run only in the existing GKE cluster, namespace `maliev-legacy`; no new node pool, Cloud SQL,
  or other paid infrastructure.
- Keep logs at Warning by default and never log supplier data, purchase-order contents, tokens,
  request bodies, object URLs, idempotency keys, or headers.
- All routes are authenticated and permission-protected. Destructive and purchase-order
  state-changing operations require live checks; critical operations are explicitly marked.

## Validation and commits

- Cross-boundary changes require route/DTO tests plus PostgreSQL 18 integration tests for both
  databases. Concurrency and idempotency behavior must remain covered.
- Run build, tests, format verification, package vulnerability audit, and gitleaks.
- Commit coherent validated slices; do not mix unrelated changes.
