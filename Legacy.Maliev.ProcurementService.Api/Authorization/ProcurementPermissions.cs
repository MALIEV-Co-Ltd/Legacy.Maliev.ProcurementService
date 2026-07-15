namespace Legacy.Maliev.ProcurementService.Api.Authorization;

/// <summary>Granular staff permissions for legacy procurement operations.</summary>
public static class ProcurementPermissions
{
    /// <summary>Reads suppliers.</summary>
    public const string SuppliersRead = "legacy-procurement.suppliers.read";
    /// <summary>Creates suppliers.</summary>
    public const string SuppliersCreate = "legacy-procurement.suppliers.create";
    /// <summary>Updates suppliers.</summary>
    public const string SuppliersUpdate = "legacy-procurement.suppliers.update";
    /// <summary>Deletes suppliers.</summary>
    public const string SuppliersDelete = "legacy-procurement.suppliers.delete";
    /// <summary>Reads supplier addresses.</summary>
    public const string SupplierAddressesRead = "legacy-procurement.supplier-addresses.read";
    /// <summary>Writes supplier addresses.</summary>
    public const string SupplierAddressesWrite = "legacy-procurement.supplier-addresses.write";
    /// <summary>Deletes supplier addresses.</summary>
    public const string SupplierAddressesDelete = "legacy-procurement.supplier-addresses.delete";
    /// <summary>Reads purchase orders.</summary>
    public const string PurchaseOrdersRead = "legacy-procurement.purchase-orders.read";
    /// <summary>Creates purchase orders.</summary>
    public const string PurchaseOrdersCreate = "legacy-procurement.purchase-orders.create";
    /// <summary>Updates purchase orders.</summary>
    public const string PurchaseOrdersUpdate = "legacy-procurement.purchase-orders.update";
    /// <summary>Deletes purchase orders.</summary>
    public const string PurchaseOrdersDelete = "legacy-procurement.purchase-orders.delete";
    /// <summary>Reads purchase-order addresses.</summary>
    public const string PurchaseOrderAddressesRead = "legacy-procurement.purchase-order-addresses.read";
    /// <summary>Writes purchase-order addresses.</summary>
    public const string PurchaseOrderAddressesWrite = "legacy-procurement.purchase-order-addresses.write";
    /// <summary>Deletes purchase-order addresses.</summary>
    public const string PurchaseOrderAddressesDelete = "legacy-procurement.purchase-order-addresses.delete";
    /// <summary>Reads order items.</summary>
    public const string OrderItemsRead = "legacy-procurement.order-items.read";
    /// <summary>Writes order items.</summary>
    public const string OrderItemsWrite = "legacy-procurement.order-items.write";
    /// <summary>Deletes order items.</summary>
    public const string OrderItemsDelete = "legacy-procurement.order-items.delete";
    /// <summary>Reads purchase-order file metadata.</summary>
    public const string FilesRead = "legacy-procurement.files.read";
    /// <summary>Writes purchase-order file metadata.</summary>
    public const string FilesWrite = "legacy-procurement.files.write";
    /// <summary>Deletes purchase-order file metadata.</summary>
    public const string FilesDelete = "legacy-procurement.files.delete";
}
