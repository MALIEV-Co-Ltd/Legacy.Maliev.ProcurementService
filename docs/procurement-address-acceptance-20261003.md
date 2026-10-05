# Address HTTP acceptance candidate

This is unexecuted test preparation, not completed source parity. Source obligation:
`5fac706a7983a6d359b39acbd670e6800afe020e` (initial commit, no parents).
Committed source head observed before preparation and rechecked afterward:
`135e526d0dab85c415b3afdcefd7b70fe2c82e2f`.

Source paths include Supplier and PurchaseOrder `Controllers/AddressesController.cs`,
their independent Address models/contexts and address tests. Runtime ownership is
`Legacy.Maliev.ProcurementService`; disposition remains pending under issue #29.

| Method | Runtime route | Drafted acceptance |
| --- | --- | --- |
| POST | `/suppliers/{supplierId}/addresses` | Attached row, Location, missing parent, denied write, required line |
| GET | `/suppliers/{supplierId}/addresses` | Attached read, update visibility, missing/deleted record |
| GET | `/suppliers/addresses/{addressId}` | Location read, PascalCase/null omission, missing/deleted record |
| PUT | `/suppliers/addresses/{addressId}` | Database readback, denied write, missing record, required line |
| DELETE | `/suppliers/{supplierId}/addresses/{addressId}` | Exact service live-check admission, detach/delete, missing retry, independent PurchaseOrder row survives |
| POST | `/purchaseorders/addresses` | Exact service live-check admission, create, denied opt-in/employee, required line |
| GET | `/purchaseorders/addresses` | Empty 404, populated list |
| GET | `/purchaseorders/addresses/{addressId}` | Location read, PascalCase/null omission, missing/deleted record |
| PUT | `/purchaseorders/addresses/{addressId}` | Update readback, CreatedDate preservation, ModifiedDate advance, missing record, required line |
| DELETE | `/purchaseorders/addresses/{addressId}` | Delete readback, missing retry |

Supplier `Address1`/`Address2` and PurchaseOrder `AddressLine1`/`AddressLine2`
remain isolated databases. Tests use existing PostgreSQL18 containers and real
Production RS256 middleware, application services and repositories. PurchaseOrder
and deletion positive controls use existing explicit trusted-service opt-in,
not a replacement IAM handler. This does not prove employee live IAM integration.

Original separate services reused the `GetAddress` named route; consolidation uses
`GetSupplierAddressRecord` and `GetPurchaseOrderAddress`. Tests assert emitted
Location resolves to the corresponding record. No source retirement is claimed.
Existing required-line/country validation and owner-restricted supplier deletion
must be assessed as compatibility/security policies, not silently equated to the
original controller's null-body-only checks and unrestricted address lookup.

Two additional candidates exercise database/security failure boundaries. A
PurchaseOrder with ShippingAddressId and BillingAddressId pointing to one address
must survive the rejected address delete, with its FK references intact and no
database detail disclosed in the HTTP error. Source optional Billing/Shipping
relationships have no configured database cascade, while target uses explicit
NoAction; actual source SQL deletion was not executed. A wrong-owner Supplier
delete expects404 and both attachments intact under existing target security
policy. The original source lookup did not restrict address ownership, so this
case is not labelled identical source behavior.

The same initial-source bundle now includes two child lifecycle cases under
`ProcurementChildLifecycleTests`: five OrderItem actions with computed decimal
readback and parent-scoped lists, and five file-metadata actions with encoded
bucket/object query values, resolving Location, updates and delete/missing outcomes.
Source paths are PurchaseOrderService FilesController/OrderItemsController,
PurchaseOrderContext/OrderItem/PurchaseOrderFile and their original tests. Source
Subtotal is decimal(18,2) conversion of UnitPrice*Quantity; the candidate checks
37.02 and0.07 through both PostgreSQL and HTTP. Five additional arithmetic cases cover null quantity, null price, both null, zero and negative quantity. Each transitions to a finite6.90 subtotal and back to the original operands, rejecting stale computed values through HTTP and database readback. File rows remain bucket/object
metadata and never invoke GCS. Optional concurrency and idempotency compatibility
remain separate existing tests/obligations; lifecycle tests do not waive them.

No production/runtime edit has been made. Build, twenty-one new cases, full suite,
unexcluded owned-assembly coverage >=80%, formatting, dependency audit, secret scan,
joined BFF/employee IAM acceptance and protected-main exact-head CI remain pending.

Review follow-up: both address schemas now exercise populated Building, secondary line, City, State, PostalCode and changed CountryId through create/update HTTP and database readback. Existing null-omission cases remain separate. Child Location resolves the full expected record, and lifecycle timestamps must be populated and advance on updates.
