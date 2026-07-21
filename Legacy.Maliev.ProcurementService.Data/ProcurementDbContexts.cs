using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Data;

/// <summary>Preserves the legacy Supplier database as an independent EF boundary.</summary>
public sealed class SupplierDbContext(DbContextOptions<SupplierDbContext> options) : DbContext(options)
{
    /// <summary>Supplier records.</summary>
    public DbSet<Supplier> Suppliers => Set<Supplier>();
    /// <summary>Supplier-database addresses.</summary>
    public DbSet<SupplierAddress> Addresses => Set<SupplierAddress>();

    /// <inheritdoc />
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        var address = modelBuilder.Entity<SupplierAddress>();
        address.ToTable("Address");
        address.HasKey(value => value.Id);
        address.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        address.Property(value => value.Address1).HasMaxLength(256);
        address.Property(value => value.Address2).HasMaxLength(256);
        address.Property(value => value.Building).HasMaxLength(256);
        address.Property(value => value.City).HasMaxLength(256);
        address.Property(value => value.CountryId).HasColumnName("CountryID");
        address.Property(value => value.PostalCode).HasMaxLength(256);
        address.Property(value => value.State).HasMaxLength(256);
        ConfigureDates(address);

        var supplier = modelBuilder.Entity<Supplier>();
        supplier.ToTable("Supplier");
        supplier.HasKey(value => value.Id);
        supplier.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        supplier.Property(value => value.AddressId).HasColumnName("AddressID");
        supplier.Property(value => value.Email).HasMaxLength(256);
        supplier.Property(value => value.Fax).HasMaxLength(256);
        supplier.Property(value => value.Mobile).HasMaxLength(256);
        supplier.Property(value => value.Name).HasMaxLength(256);
        supplier.Property(value => value.Note).HasColumnType("text");
        supplier.Property(value => value.TaxNumber).HasMaxLength(256);
        supplier.Property(value => value.Telephone).HasMaxLength(256);
        supplier.Property(value => value.Website).HasMaxLength(256);
        ConfigureDates(supplier);
        supplier.HasOne(value => value.Address)
            .WithMany(value => value.Suppliers)
            .HasForeignKey(value => value.AddressId)
            .OnDelete(DeleteBehavior.NoAction)
            .HasConstraintName("FK_Supplier_Address");
    }

    private static void ConfigureDates<TEntity>(Microsoft.EntityFrameworkCore.Metadata.Builders.EntityTypeBuilder<TEntity> entity) where TEntity : class
    {
        entity.Property<DateTime?>("CreatedDate").HasColumnType("timestamp without time zone").HasDefaultValueSql("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'");
        entity.Property<DateTime?>("ModifiedDate").HasColumnType("timestamp without time zone").HasDefaultValueSql("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'");
    }
}

/// <summary>Preserves the legacy PurchaseOrder database as an independent EF boundary.</summary>
public sealed class PurchaseOrderDbContext(DbContextOptions<PurchaseOrderDbContext> options) : DbContext(options)
{
    /// <summary>Purchase orders.</summary>
    public DbSet<PurchaseOrder> PurchaseOrders => Set<PurchaseOrder>();
    /// <summary>PurchaseOrder-database addresses.</summary>
    public DbSet<PurchaseOrderAddress> Addresses => Set<PurchaseOrderAddress>();
    /// <summary>Purchase-order line items.</summary>
    public DbSet<OrderItem> OrderItems => Set<OrderItem>();
    /// <summary>Purchase-order file metadata.</summary>
    public DbSet<PurchaseOrderFile> Files => Set<PurchaseOrderFile>();

    /// <inheritdoc />
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        var address = modelBuilder.Entity<PurchaseOrderAddress>();
        address.ToTable("Address");
        address.HasKey(value => value.Id);
        address.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        address.Property(value => value.AddressLine1).HasMaxLength(256).IsRequired();
        address.Property(value => value.AddressLine2).HasMaxLength(256);
        address.Property(value => value.Building).HasMaxLength(256);
        address.Property(value => value.City).HasMaxLength(256);
        address.Property(value => value.CountryId).HasColumnName("CountryID");
        address.Property(value => value.PostalCode).HasMaxLength(256);
        address.Property(value => value.State).HasMaxLength(256);
        ConfigureDates(address);

        var purchaseOrder = modelBuilder.Entity<PurchaseOrder>();
        purchaseOrder.ToTable("PurchaseOrder");
        purchaseOrder.HasKey(value => value.Id);
        purchaseOrder.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        purchaseOrder.Property(value => value.BillingAddressId).HasColumnName("BillingAddressID");
        purchaseOrder.Property(value => value.BillingContactPerson).HasMaxLength(256);
        purchaseOrder.Property(value => value.BillingFax).HasMaxLength(256);
        purchaseOrder.Property(value => value.BillingMobile).HasMaxLength(256);
        purchaseOrder.Property(value => value.BillingTelephone).HasMaxLength(256);
        purchaseOrder.Property(value => value.EmployeeId).HasColumnName("EmployeeID");
        purchaseOrder.Property(value => value.Fob).HasColumnName("FOB");
        purchaseOrder.Property(value => value.ShippingAddressId).HasColumnName("ShippingAddressID");
        purchaseOrder.Property(value => value.ShippingContactPerson).HasMaxLength(256);
        purchaseOrder.Property(value => value.ShippingFax).HasMaxLength(256);
        purchaseOrder.Property(value => value.ShippingMethod).HasMaxLength(256);
        purchaseOrder.Property(value => value.ShippingMobile).HasMaxLength(256);
        purchaseOrder.Property(value => value.ShippingTelephone).HasMaxLength(256);
        purchaseOrder.Property(value => value.SupplierContactPerson).HasMaxLength(256);
        purchaseOrder.Property(value => value.SupplierId).HasColumnName("SupplierID");
        purchaseOrder.Property(value => value.Terms).HasMaxLength(256);
        ConfigureDates(purchaseOrder);
        purchaseOrder.Property(value => value.ModifiedDate).IsConcurrencyToken();
        purchaseOrder.HasOne(value => value.BillingAddress)
            .WithMany(value => value.BillingPurchaseOrders)
            .HasForeignKey(value => value.BillingAddressId)
            .OnDelete(DeleteBehavior.NoAction)
            .HasConstraintName("FK_PurchaseOrder_Address1");
        purchaseOrder.HasOne(value => value.ShippingAddress)
            .WithMany(value => value.ShippingPurchaseOrders)
            .HasForeignKey(value => value.ShippingAddressId)
            .OnDelete(DeleteBehavior.NoAction)
            .HasConstraintName("FK_PurchaseOrder_Address");

        var orderItem = modelBuilder.Entity<OrderItem>();
        orderItem.ToTable("OrderItem");
        orderItem.HasKey(value => value.Id);
        orderItem.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        orderItem.Property(value => value.PartNumber).HasMaxLength(100);
        orderItem.Property(value => value.PurchaseOrderId).HasColumnName("PurchaseOrderID");
        orderItem.Property(value => value.UnitPrice).HasColumnType("numeric(18,2)");
        orderItem.Property(value => value.Subtotal).HasColumnType("numeric(18,2)")
            .HasComputedColumnSql("(\"UnitPrice\" * \"Quantity\")::numeric(18,2)", stored: true);
        ConfigureDates(orderItem);
        orderItem.Property(value => value.ModifiedDate).IsConcurrencyToken();
        orderItem.HasOne(value => value.PurchaseOrder)
            .WithMany(value => value.OrderItems)
            .HasForeignKey(value => value.PurchaseOrderId)
            .OnDelete(DeleteBehavior.NoAction)
            .HasConstraintName("FK_OrderItem_PurchaseOrder");

        var file = modelBuilder.Entity<PurchaseOrderFile>();
        file.ToTable("PurchaseOrderFile");
        file.HasKey(value => value.Id);
        file.Property(value => value.Id).HasColumnName("ID").ValueGeneratedOnAdd();
        file.Property(value => value.PurchaseOrderId).HasColumnName("PurchaseOrderID");
        file.Property(value => value.Bucket).HasMaxLength(50).IsRequired();
        file.Property(value => value.ObjectName).IsRequired();
        ConfigureDates(file);
        file.HasOne(value => value.PurchaseOrder)
            .WithMany(value => value.Files)
            .HasForeignKey(value => value.PurchaseOrderId)
            .OnDelete(DeleteBehavior.NoAction)
            .HasConstraintName("FK_PurchaseOrderFile_PurchaseOrder");
    }

    private static void ConfigureDates<TEntity>(Microsoft.EntityFrameworkCore.Metadata.Builders.EntityTypeBuilder<TEntity> entity) where TEntity : class
    {
        entity.Property<DateTime?>("CreatedDate").HasColumnType("timestamp without time zone").HasDefaultValueSql("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'");
        entity.Property<DateTime?>("ModifiedDate").HasColumnType("timestamp without time zone").HasDefaultValueSql("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'");
    }
}
