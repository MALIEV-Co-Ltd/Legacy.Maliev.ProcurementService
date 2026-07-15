namespace Legacy.Maliev.ProcurementService.Domain;

/// <summary>Legacy supplier master record.</summary>
public sealed class Supplier
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>Supplier name.</summary>
    public string? Name { get; set; }
    /// <summary>Supplier website.</summary>
    public string? Website { get; set; }
    /// <summary>Supplier tax number.</summary>
    public string? TaxNumber { get; set; }
    /// <summary>Supplier email.</summary>
    public string? Email { get; set; }
    /// <summary>Internal note.</summary>
    public string? Note { get; set; }
    /// <summary>Optional supplier address identifier.</summary>
    public int? AddressId { get; set; }
    /// <summary>Supplier telephone.</summary>
    public string? Telephone { get; set; }
    /// <summary>Supplier mobile.</summary>
    public string? Mobile { get; set; }
    /// <summary>Supplier fax.</summary>
    public string? Fax { get; set; }
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>Related supplier address.</summary>
    public SupplierAddress? Address { get; set; }
}

/// <summary>Address table owned by the legacy Supplier database.</summary>
public sealed class SupplierAddress
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>Building.</summary>
    public string? Building { get; set; }
    /// <summary>Primary address line using the Supplier schema name.</summary>
    public string? Address1 { get; set; }
    /// <summary>Secondary address line using the Supplier schema name.</summary>
    public string? Address2 { get; set; }
    /// <summary>City.</summary>
    public string? City { get; set; }
    /// <summary>State.</summary>
    public string? State { get; set; }
    /// <summary>Postal code.</summary>
    public string? PostalCode { get; set; }
    /// <summary>Country identifier.</summary>
    public int CountryId { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>Suppliers using this address.</summary>
    public ICollection<Supplier> Suppliers { get; } = [];
}

/// <summary>Legacy purchase order.</summary>
public sealed class PurchaseOrder
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>External Supplier database identifier.</summary>
    public int? SupplierId { get; set; }
    /// <summary>Supplier contact person.</summary>
    public string? SupplierContactPerson { get; set; }
    /// <summary>Shipping address identifier.</summary>
    public int? ShippingAddressId { get; set; }
    /// <summary>Shipping contact person.</summary>
    public string? ShippingContactPerson { get; set; }
    /// <summary>Shipping telephone.</summary>
    public string? ShippingTelephone { get; set; }
    /// <summary>Shipping mobile.</summary>
    public string? ShippingMobile { get; set; }
    /// <summary>Shipping fax.</summary>
    public string? ShippingFax { get; set; }
    /// <summary>Billing address identifier.</summary>
    public int? BillingAddressId { get; set; }
    /// <summary>Billing contact person.</summary>
    public string? BillingContactPerson { get; set; }
    /// <summary>Billing telephone.</summary>
    public string? BillingTelephone { get; set; }
    /// <summary>Billing mobile.</summary>
    public string? BillingMobile { get; set; }
    /// <summary>Billing fax.</summary>
    public string? BillingFax { get; set; }
    /// <summary>Freight-on-board text.</summary>
    public string? Fob { get; set; }
    /// <summary>Payment terms.</summary>
    public string? Terms { get; set; }
    /// <summary>Shipping method.</summary>
    public string? ShippingMethod { get; set; }
    /// <summary>External Employee database identifier.</summary>
    public int? EmployeeId { get; set; }
    /// <summary>Internal notes.</summary>
    public string? Notes { get; set; }
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>Billing address.</summary>
    public PurchaseOrderAddress? BillingAddress { get; set; }
    /// <summary>Shipping address.</summary>
    public PurchaseOrderAddress? ShippingAddress { get; set; }
    /// <summary>Order items.</summary>
    public ICollection<OrderItem> OrderItems { get; } = [];
    /// <summary>GCS object metadata rows.</summary>
    public ICollection<PurchaseOrderFile> Files { get; } = [];
}

/// <summary>Address table owned by the legacy PurchaseOrder database.</summary>
public sealed class PurchaseOrderAddress
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>Building.</summary>
    public string? Building { get; set; }
    /// <summary>Primary address line.</summary>
    public string AddressLine1 { get; set; } = string.Empty;
    /// <summary>Secondary address line.</summary>
    public string? AddressLine2 { get; set; }
    /// <summary>City.</summary>
    public string? City { get; set; }
    /// <summary>State.</summary>
    public string? State { get; set; }
    /// <summary>Postal code.</summary>
    public string? PostalCode { get; set; }
    /// <summary>Country identifier.</summary>
    public int CountryId { get; set; }
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>Purchase orders using the address for billing.</summary>
    public ICollection<PurchaseOrder> BillingPurchaseOrders { get; } = [];
    /// <summary>Purchase orders using the address for shipping.</summary>
    public ICollection<PurchaseOrder> ShippingPurchaseOrders { get; } = [];
}

/// <summary>Legacy purchase-order line item.</summary>
public sealed class OrderItem
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>Purchase-order identifier.</summary>
    public int? PurchaseOrderId { get; set; }
    /// <summary>Part number.</summary>
    public string? PartNumber { get; set; }
    /// <summary>Description.</summary>
    public string? Description { get; set; }
    /// <summary>Quantity.</summary>
    public int? Quantity { get; set; }
    /// <summary>Unit price.</summary>
    public decimal? UnitPrice { get; set; }
    /// <summary>Database-computed subtotal.</summary>
    public decimal? Subtotal { get; private set; }
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>Owning purchase order.</summary>
    public PurchaseOrder? PurchaseOrder { get; set; }
}

/// <summary>Google Cloud Storage metadata for a purchase-order file.</summary>
public sealed class PurchaseOrderFile
{
    /// <summary>Legacy identifier.</summary>
    public int Id { get; set; }
    /// <summary>Owning purchase-order identifier.</summary>
    public int PurchaseOrderId { get; set; }
    /// <summary>GCS bucket.</summary>
    public string Bucket { get; set; } = string.Empty;
    /// <summary>GCS object name.</summary>
    public string ObjectName { get; set; } = string.Empty;
    /// <summary>UTC creation time.</summary>
    public DateTime? CreatedDate { get; set; }
    /// <summary>UTC modification time.</summary>
    public DateTime? ModifiedDate { get; set; }
    /// <summary>Owning purchase order.</summary>
    public PurchaseOrder? PurchaseOrder { get; set; }
}
