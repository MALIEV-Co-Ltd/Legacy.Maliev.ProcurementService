using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Testcontainers.PostgreSql;

namespace Legacy.Maliev.ProcurementService.Tests.Data;

public sealed class ProcurementPostgresMigrationTests : IAsyncLifetime
{
    private readonly PostgreSqlContainer supplierPostgres = new PostgreSqlBuilder("postgres:18-alpine").Build();
    private readonly PostgreSqlContainer purchaseOrderPostgres = new PostgreSqlBuilder("postgres:18-alpine").Build();

    public Task InitializeAsync() => Task.WhenAll(supplierPostgres.StartAsync(), purchaseOrderPostgres.StartAsync());

    public async Task DisposeAsync()
    {
        await supplierPostgres.DisposeAsync();
        await purchaseOrderPostgres.DisposeAsync();
    }

    [Fact]
    public async Task InitialMigrations_PreserveBothIndependentSchemasAndRepositoryBehavior()
    {
        await using var supplierContext = CreateSupplierContext();
        await using var orderContext = CreatePurchaseOrderContext();
        await Task.WhenAll(supplierContext.Database.MigrateAsync(), orderContext.Database.MigrateAsync());
        var suppliers = new SupplierRepository(supplierContext, TimeProvider.System);
        var orders = new PurchaseOrderRepository(orderContext, TimeProvider.System);

        var supplier = await suppliers.CreateSupplierAsync(
            new("Thai Materials", "https://example.test", "TAX-7", "buyer@example.test", "legacy", "02", "08", null),
            CancellationToken.None);
        var supplierAddress = await suppliers.CreateAddressAsync(
            supplier.Id,
            new("A", "1 Legacy Road", null, "Bangkok", null, "10110", 764),
            CancellationToken.None);
        var purchaseOrder = await orders.CreatePurchaseOrderAsync(
            PurchaseOrderRequest(supplier.Id, "Original supplier contact", "migration"),
            CancellationToken.None);
        var orderAddress = await orders.CreateAddressAsync(
            new("B", "2 Purchase Road", null, "Bangkok", null, "10260", 764),
            CancellationToken.None);
        var orderItem = await orders.CreateOrderItemAsync(
            new(purchaseOrder.Id, "MAT-1", "Resin", 3, 125.50m),
            CancellationToken.None);
        var file = await orders.CreateFileAsync(purchaseOrder.Id, "maliev-legacy", "purchase-orders/1.pdf", CancellationToken.None);

        Assert.Equal("1 Legacy Road", supplierAddress?.Address1);
        Assert.Equal("Original supplier contact", purchaseOrder.SupplierContactPerson);
        Assert.Equal("2 Purchase Road", orderAddress.AddressLine1);
        Assert.Equal(376.50m, orderItem.Subtotal);
        Assert.Equal("purchase-orders/1.pdf", file?.ObjectName);
        Assert.Equal(2, await supplierContext.Database.SqlQueryRaw<int>(
            "SELECT COUNT(*)::int AS \"Value\" FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('Address', 'Supplier')").SingleAsync());
        Assert.Equal(4, await orderContext.Database.SqlQueryRaw<int>(
            "SELECT COUNT(*)::int AS \"Value\" FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('Address', 'PurchaseOrder', 'OrderItem', 'PurchaseOrderFile')").SingleAsync());
        Assert.Equal(0, await supplierContext.Database.SqlQueryRaw<int>(
            "SELECT COUNT(*)::int AS \"Value\" FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('PurchaseOrder', 'OrderItem', 'PurchaseOrderFile')").SingleAsync());
        Assert.Equal(0, await orderContext.Database.SqlQueryRaw<int>(
            "SELECT COUNT(*)::int AS \"Value\" FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'Supplier'").SingleAsync());
    }

    [Fact]
    public async Task ModifiedDateConcurrency_RejectsStalePurchaseOrderAndOrderItemUpdates()
    {
        await using var setupContext = CreatePurchaseOrderContext();
        await setupContext.Database.MigrateAsync();
        var setup = new PurchaseOrderRepository(setupContext, TimeProvider.System);
        var order = await setup.CreatePurchaseOrderAsync(PurchaseOrderRequest(null, "first", "first"), CancellationToken.None);
        var item = await setup.CreateOrderItemAsync(new(order.Id, "A", "first", 1, 10m), CancellationToken.None);
        var staleOrderDate = order.ModifiedDate!.Value;
        var staleItemDate = item.ModifiedDate!.Value;
        await setupContext.PurchaseOrders.Where(x => x.Id == order.Id).ExecuteUpdateAsync(setters => setters.SetProperty(x => x.ModifiedDate, staleOrderDate.AddMinutes(1)));
        await setupContext.OrderItems.Where(x => x.Id == item.Id).ExecuteUpdateAsync(setters => setters.SetProperty(x => x.ModifiedDate, staleItemDate.AddMinutes(1)));
        setupContext.ChangeTracker.Clear();
        var repository = new PurchaseOrderRepository(setupContext, TimeProvider.System);

        var orderResult = await repository.UpdatePurchaseOrderAsync(order.Id, PurchaseOrderRequest(null, "stale", "stale"), new DateTimeOffset(staleOrderDate), CancellationToken.None);
        setupContext.ChangeTracker.Clear();
        var itemResult = await repository.UpdateOrderItemAsync(item.Id, new(order.Id, "A", "stale", 2, 10m), new DateTimeOffset(staleItemDate), CancellationToken.None);

        Assert.Equal(UpdateResult.Conflict, orderResult);
        Assert.Equal(UpdateResult.Conflict, itemResult);
    }

    private static UpsertPurchaseOrderRequest PurchaseOrderRequest(int? supplierId, string contact, string notes) =>
        new(
            SupplierId: supplierId,
            SupplierContactPerson: contact,
            ShippingAddressId: null,
            ShippingContactPerson: null,
            ShippingTelephone: null,
            ShippingMobile: null,
            ShippingFax: null,
            BillingAddressId: null,
            BillingContactPerson: null,
            BillingTelephone: null,
            BillingMobile: null,
            BillingFax: null,
            Fob: null,
            Terms: null,
            ShippingMethod: null,
            EmployeeId: null,
            Notes: notes);

    private SupplierDbContext CreateSupplierContext() => new(
        new DbContextOptionsBuilder<SupplierDbContext>().UseNpgsql(supplierPostgres.GetConnectionString()).Options);

    private PurchaseOrderDbContext CreatePurchaseOrderContext() => new(
        new DbContextOptionsBuilder<PurchaseOrderDbContext>().UseNpgsql(purchaseOrderPostgres.GetConnectionString()).Options);

}
