namespace Legacy.Maliev.ProcurementService.Application.Models;

/// <summary>Legacy supplier response.</summary>
public sealed record SupplierResponse(int Id, string? Name, string? Website, string? TaxNumber, string? Email, string? Note, int? AddressId, string? Telephone, string? Mobile, string? Fax, DateTime? CreatedDate, DateTime? ModifiedDate);
/// <summary>Legacy Supplier-database address response.</summary>
public sealed record SupplierAddressResponse(int Id, string? Building, string? Address1, string? Address2, string? City, string? State, string? PostalCode, int CountryId, DateTime? ModifiedDate, DateTime? CreatedDate);
/// <summary>Supplier create/update request.</summary>
public sealed record UpsertSupplierRequest(string? Name, string? Website, string? TaxNumber, string? Email, string? Note, string? Telephone, string? Mobile, string? Fax);
/// <summary>Supplier address create/update request.</summary>
public sealed record UpsertSupplierAddressRequest(string? Building, string? Address1, string? Address2, string? City, string? State, string? PostalCode, int CountryId);

/// <summary>Legacy purchase-order response.</summary>
public sealed record PurchaseOrderResponse(
    int Id, int? SupplierId, string? SupplierContactPerson, int? ShippingAddressId, string? ShippingContactPerson,
    string? ShippingTelephone, string? ShippingMobile, string? ShippingFax, int? BillingAddressId,
    string? BillingContactPerson, string? BillingTelephone, string? BillingMobile, string? BillingFax,
    string? Fob, string? Terms, string? ShippingMethod, int? EmployeeId, string? Notes,
    DateTime? CreatedDate, DateTime? ModifiedDate);

/// <summary>Purchase-order create/update request.</summary>
public sealed record UpsertPurchaseOrderRequest(
    int? SupplierId, string? SupplierContactPerson, int? ShippingAddressId, string? ShippingContactPerson,
    string? ShippingTelephone, string? ShippingMobile, string? ShippingFax, int? BillingAddressId,
    string? BillingContactPerson, string? BillingTelephone, string? BillingMobile, string? BillingFax,
    string? Fob, string? Terms, string? ShippingMethod, int? EmployeeId, string? Notes);

/// <summary>Legacy PurchaseOrder-database address response.</summary>
public sealed record PurchaseOrderAddressResponse(int Id, string? Building, string AddressLine1, string? AddressLine2, string? City, string? State, string? PostalCode, int CountryId, DateTime? CreatedDate, DateTime? ModifiedDate);
/// <summary>PurchaseOrder address create/update request.</summary>
public sealed record UpsertPurchaseOrderAddressRequest(string? Building, string AddressLine1, string? AddressLine2, string? City, string? State, string? PostalCode, int CountryId);
/// <summary>Legacy order-item response.</summary>
public sealed record OrderItemResponse(int Id, int? PurchaseOrderId, string? PartNumber, string? Description, int? Quantity, decimal? UnitPrice, decimal? Subtotal, DateTime? CreatedDate, DateTime? ModifiedDate);
/// <summary>Order-item create/update request.</summary>
public sealed record UpsertOrderItemRequest(int? PurchaseOrderId, string? PartNumber, string? Description, int? Quantity, decimal? UnitPrice);
/// <summary>Legacy purchase-order GCS object metadata response.</summary>
public sealed record PurchaseOrderFileResponse(int Id, int PurchaseOrderId, string Bucket, string ObjectName, DateTime? CreatedDate, DateTime? ModifiedDate);
/// <summary>Purchase-order file metadata update request.</summary>
public sealed record UpsertPurchaseOrderFileRequest(int? PurchaseOrderId, string Bucket, string ObjectName);

/// <summary>Preserves legacy pagination fields.</summary>
public sealed record PaginatedResponse<T>(IReadOnlyList<T> Items, int PageIndex, int TotalPages, int TotalRecords)
{
    /// <summary>Whether another page exists.</summary>
    public bool HasNextPage => PageIndex < TotalPages;
    /// <summary>Whether a previous page exists.</summary>
    public bool HasPreviousPage => PageIndex > 1;
}

/// <summary>Legacy supplier sort names and values.</summary>
public enum SupplierSortType
{
    /// <summary>Identifier ascending.</summary>
    SupplierId_Ascending,
    /// <summary>Identifier descending.</summary>
    SupplierId_Descending,
    /// <summary>Name ascending.</summary>
    SupplierName_Ascending,
    /// <summary>Name descending.</summary>
    SupplierName_Descending,
    /// <summary>Created time ascending.</summary>
    SupplierCreatedDate_Ascending,
    /// <summary>Created time descending.</summary>
    SupplierCreatedDate_Descending,
    /// <summary>Modified time ascending.</summary>
    SupplierModifiedDate_Ascending,
    /// <summary>Modified time descending.</summary>
    SupplierModifiedDate_Descending,
}

/// <summary>Legacy purchase-order sort names and values.</summary>
public enum PurchaseOrderSortType
{
    /// <summary>Identifier ascending.</summary>
    PurchaseOrderId_Ascending,
    /// <summary>Identifier descending.</summary>
    PurchaseOrderId_Descending,
    /// <summary>Created time ascending.</summary>
    PurchaseOrderCreatedDate_Ascending,
    /// <summary>Created time descending.</summary>
    PurchaseOrderCreatedDate_Descending,
}

/// <summary>Optimistic-concurrency result without adding a legacy database column.</summary>
public enum UpdateResult
{
    /// <summary>Record was updated.</summary>
    Updated,
    /// <summary>Record was not found.</summary>
    NotFound,
    /// <summary>Expected modification time did not match.</summary>
    Conflict,
}
