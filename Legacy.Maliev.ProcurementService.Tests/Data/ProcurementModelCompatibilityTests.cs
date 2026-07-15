using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;

namespace Legacy.Maliev.ProcurementService.Tests.Data;

public sealed class ProcurementModelCompatibilityTests
{
    [Fact]
    public void SupplierAndPurchaseOrderAddresses_RemainIsolatedLegacySchemas()
    {
        using var supplier = CreateSupplierContext();
        using var purchaseOrder = CreatePurchaseOrderContext();
        var supplierAddress = supplier.Model.FindEntityType(typeof(SupplierAddress))!;
        var orderAddress = purchaseOrder.Model.FindEntityType(typeof(PurchaseOrderAddress))!;

        Assert.Equal("Address", supplierAddress.GetTableName());
        Assert.Equal("Address1", supplierAddress.FindProperty(nameof(SupplierAddress.Address1))!.GetColumnName());
        Assert.Null(supplierAddress.FindProperty(nameof(PurchaseOrderAddress.AddressLine1)));
        Assert.Equal("Address", orderAddress.GetTableName());
        Assert.Equal("AddressLine1", orderAddress.FindProperty(nameof(PurchaseOrderAddress.AddressLine1))!.GetColumnName());
        Assert.Null(orderAddress.FindProperty(nameof(SupplierAddress.Address1)));
    }

    [Fact]
    public void PurchaseOrderModel_PreservesTablesRelationsComputedSubtotalAndDateConcurrency()
    {
        using var context = CreatePurchaseOrderContext();
        var order = context.Model.FindEntityType(typeof(PurchaseOrder))!;
        var item = context.Model.FindEntityType(typeof(OrderItem))!;

        Assert.Equal("PurchaseOrder", order.GetTableName());
        Assert.Equal("OrderItem", item.GetTableName());
        Assert.Equal("PurchaseOrderFile", context.Model.FindEntityType(typeof(PurchaseOrderFile))!.GetTableName());
        Assert.True(order.FindProperty(nameof(PurchaseOrder.ModifiedDate))!.IsConcurrencyToken);
        Assert.True(item.FindProperty(nameof(OrderItem.ModifiedDate))!.IsConcurrencyToken);
        Assert.Contains("UnitPrice", item.FindProperty(nameof(OrderItem.Subtotal))!.GetComputedColumnSql());
        Assert.DoesNotContain(order.GetProperties(), property => property.Name.Equals("xmin", StringComparison.OrdinalIgnoreCase));
        Assert.Collection(
            order.GetForeignKeys().Select(key => key.GetConstraintName()).Order(),
            name => Assert.Equal("FK_PurchaseOrder_Address", name),
            name => Assert.Equal("FK_PurchaseOrder_Address1", name));
    }

    private static SupplierDbContext CreateSupplierContext() => new(
        new DbContextOptionsBuilder<SupplierDbContext>().UseNpgsql("Host=localhost;Database=supplier-model").Options);

    private static PurchaseOrderDbContext CreatePurchaseOrderContext() => new(
        new DbContextOptionsBuilder<PurchaseOrderDbContext>().UseNpgsql("Host=localhost;Database=purchase-order-model").Options);
}
