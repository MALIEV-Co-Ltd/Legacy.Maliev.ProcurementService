#nullable disable
// Inert retained body declarations; no context, controllers, SDK or financial execution.
// Source: MALIEV-Co-Ltd/maliev-web@5fac706a7983a6d359b39acbd670e6800afe020e.
// Maliev.SupplierService.Data/Database/SupplierContext/Supplier.cs @ 889f0ddf257f19dfde25648fba74690e63ca3f95
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.SupplierContext
{
    using System;
    using System.Collections.Generic;

    internal partial class Supplier
    {
        public int Id { get; set; }
        public string Name { get; set; }
        public string Website { get; set; }
        public string TaxNumber { get; set; }
        public string Email { get; set; }
        public string Note { get; set; }
        public int? AddressId { get; set; }
        public string Telephone { get; set; }
        public string Mobile { get; set; }
        public string Fax { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }

        public virtual Address Address { get; set; }
    }
}

// Maliev.SupplierService.Data/Database/SupplierContext/Address.cs @ fcee648ad6caf04aea06894a491ff698e2222a5b
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.SupplierContext
{
    using System;
    using System.Collections.Generic;

    internal partial class Address
    {
        public Address()
        {
            this.Supplier = new HashSet<Supplier>();
        }

        public int Id { get; set; }
        public string Building { get; set; }
        public string Address1 { get; set; }
        public string Address2 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public int CountryId { get; set; }
        public DateTime? ModifiedDate { get; set; }
        public DateTime? CreatedDate { get; set; }

        public virtual ICollection<Supplier> Supplier { get; set; }
    }
}

// Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/Address.cs @ 9e5621659c1f3a1e06f865acc6121e15a81a9b15
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext
{
    using System;
    using System.Collections.Generic;

    internal partial class Address
    {
        public Address()
        {
            this.PurchaseOrderBillingAddress = new HashSet<PurchaseOrder>();
            this.PurchaseOrderShippingAddress = new HashSet<PurchaseOrder>();
        }

        public int Id { get; set; }
        public string Building { get; set; }
        public string AddressLine1 { get; set; }
        public string AddressLine2 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public int CountryId { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }

        public virtual ICollection<PurchaseOrder> PurchaseOrderBillingAddress { get; set; }
        public virtual ICollection<PurchaseOrder> PurchaseOrderShippingAddress { get; set; }
    }
}

// Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/PurchaseOrderFile.cs @ 555d54fc2d025fe25a595664c174a24a5b30fcba
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext
{
    using System;
    using System.Collections.Generic;

    internal partial class PurchaseOrderFile
    {
        public int Id { get; set; }
        public int PurchaseOrderId { get; set; }
        public string Bucket { get; set; }
        public string ObjectName { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }

        public virtual PurchaseOrder PurchaseOrder { get; set; }
    }
}

// Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/PurchaseOrder.cs @ f7fdd3b88523bc2d7c8ef19a4e9f5ea9a2b17d55
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext
{
    using System;
    using System.Collections.Generic;

    internal partial class PurchaseOrder
    {
        public PurchaseOrder()
        {
            this.OrderItem = new HashSet<OrderItem>();
            this.PurchaseOrderFile = new HashSet<PurchaseOrderFile>();
        }

        public int Id { get; set; }
        public int? SupplierId { get; set; }
        public string SupplierContactPerson { get; set; }
        public int? ShippingAddressId { get; set; }
        public string ShippingContactPerson { get; set; }
        public string ShippingTelephone { get; set; }
        public string ShippingMobile { get; set; }
        public string ShippingFax { get; set; }
        public int? BillingAddressId { get; set; }
        public string BillingContactPerson { get; set; }
        public string BillingTelephone { get; set; }
        public string BillingMobile { get; set; }
        public string BillingFax { get; set; }
        public string Fob { get; set; }
        public string Terms { get; set; }
        public string ShippingMethod { get; set; }
        public int? EmployeeId { get; set; }
        public string Notes { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }

        public virtual Address BillingAddress { get; set; }
        public virtual Address ShippingAddress { get; set; }
        public virtual ICollection<OrderItem> OrderItem { get; set; }
        public virtual ICollection<PurchaseOrderFile> PurchaseOrderFile { get; set; }
    }
}

// Maliev.PurchaseOrderService.Data/Database/PurchaseOrderContext/OrderItem.cs @ 5c670e8f5cef3078fe0bff2f600ca9ef14a55b49
namespace Legacy.Maliev.ProcurementService.Api.Serialization.SourceBodies.PurchaseOrderContext
{
    using System;
    using System.Collections.Generic;

    internal partial class OrderItem
    {
        public int Id { get; set; }
        public int? PurchaseOrderId { get; set; }
        public string PartNumber { get; set; }
        public string Description { get; set; }
        public int? Quantity { get; set; }
        public decimal? UnitPrice { get; set; }
        public decimal? Subtotal { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }

        public virtual PurchaseOrder PurchaseOrder { get; set; }
    }
}
