using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementRequiredAndLiteralSourceTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    public async Task FileJsonUpdatePreservesValidEmptyAndWhitespaceLiteralsWithoutCallingStorage(string literal)
    {
        await using var factory = fixture.CreateFactory(true);
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 93 });
            orders.Files.Add(new PurchaseOrderFile { Id = 94, PurchaseOrderId = 93, Bucket = "synthetic-bucket", ObjectName = "synthetic/object" });
            await orders.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
        using var updated = await client.PutAsJsonAsync("/purchaseorders/files/94", new UpsertPurchaseOrderFileRequest(93, literal, literal));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var fresh = (await client.GetFromJsonAsync<PurchaseOrderFileResponse>("/purchaseorders/files/94"))!;
        Assert.Equal(literal, fresh.Bucket);
        Assert.Equal(literal, fresh.ObjectName);
        await using var readScope = factory.Services.CreateAsyncScope();
        var row = await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().SingleAsync();
        Assert.Equal(literal, row.Bucket);
        Assert.Equal(literal, row.ObjectName);
        Assert.Empty(await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SupplierSourceExplicitRequiredPropertiesAreRequiredInTheOwnedModel(bool address)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var context = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var entity = context.Model.FindEntityType(address ? typeof(SupplierAddress) : typeof(Supplier))!;
        Assert.False(entity.FindProperty(address ? nameof(SupplierAddress.Address1) : nameof(Supplier.Name))!.IsNullable);
    }

    [Fact]
    public async Task SupplierAddressCreateKeepsAllSpaceLiteralAndUpdateKeepsSourceValidEmptyAndZeroCountry()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SupplierAddressesWrite,
            ProcurementPermissions.SupplierAddressesRead);
        using var created = await client.PostAsJsonAsync("/Suppliers", new UpsertSupplierRequest("Synthetic literal source", null, null, null, null, null, null, null));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var supplier = (await created.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var attached = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses",
            new UpsertSupplierAddressRequest(null, " ", null, null, null, null, 1));
        Assert.Equal(HttpStatusCode.Created, attached.StatusCode);
        var address = (await attached.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        using var updated = await client.PutAsJsonAsync($"/suppliers/addresses/{address.Id}",
            new UpsertSupplierAddressRequest(null, "", null, null, null, null, 0));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var fresh = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{address.Id}"))!;
        Assert.Equal("", fresh.Address1);
        Assert.Equal(0, fresh.CountryId);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var row = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().SingleAsync();
        Assert.Equal("", row.Address1);
        Assert.Equal(0, row.CountryId);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task BothOwnedDatabasesEnforceOriginalUtf16LengthWithoutTrimming(bool orderItem, bool exceeds)
    {
        int limit = orderItem ? 100 : 256;
        string literal = string.Concat(Enumerable.Repeat(char.ConvertFromUtf32(0x1F600), limit / 2 + (exceeds ? 1 : 0)));
        Assert.Equal(limit + (exceeds ? 2 : 0), literal.Length);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        DbContext context;
        if (orderItem)
        {
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.OrderItems.Add(new OrderItem { PartNumber = literal });
            context = orders;
        }
        else
        {
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Suppliers.Add(new Supplier { Name = literal });
            context = suppliers;
        }
        if (exceeds)
            await Assert.ThrowsAsync<DbUpdateException>(() => context.SaveChangesAsync());
        else
        {
            await context.SaveChangesAsync();
            context.ChangeTracker.Clear();
            string? actual = orderItem
                ? (await ((PurchaseOrderDbContext)context).OrderItems.AsNoTracking().SingleAsync()).PartNumber
                : (await ((SupplierDbContext)context).Suppliers.AsNoTracking().SingleAsync()).Name;
            Assert.Equal(literal, actual);
        }
    }
}
