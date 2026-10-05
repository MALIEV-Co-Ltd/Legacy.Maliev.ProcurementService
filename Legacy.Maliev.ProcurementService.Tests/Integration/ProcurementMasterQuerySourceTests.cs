using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementMasterQuerySourceTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task SupplierNumericSearch_SourceMatchesOnlyIdentifier_NotTextContainingSameDigits()
    {
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            database.Suppliers.AddRange(new Supplier { Id = 1234, Name = "Exact identity" },
                new Supplier { Id = 4567, Name = "Text mentions1234", Website = "https://supplier1234.invalid" });
            await database.SaveChangesAsync();
        }
        using var client = fixture.Client(ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync("/Suppliers?search=1234&index=1&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<SupplierResponse>>())!;
        Assert.Equal(1234, Assert.Single(page.Items).Id);
        Assert.Equal(1, page.TotalRecords);
        await using var readScope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Equal(2, await readScope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
    }

    [Fact]
    public async Task PurchaseOrderNumericSearch_SourceMatchesIdentifierSubstring()
    {
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.AddRange(new PurchaseOrder { Id = 203 }, new PurchaseOrder { Id = 1203 },
                new PurchaseOrder { Id = 999, Notes = "Contains203 in notes" }, new PurchaseOrder { Id = 2000 });
            await database.SaveChangesAsync();
        }
        using var client = fixture.Client(ProcurementPermissions.PurchaseOrdersRead);
        using var response = await client.GetAsync("/PurchaseOrders?search=203&index=1&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var page = (await response.Content.ReadFromJsonAsync<PaginatedResponse<PurchaseOrderResponse>>())!;
        Assert.Equal(new[] { 203, 999, 1203 }, page.Items.Select(item => item.Id));
        Assert.Equal(3, page.TotalRecords);
        await using var readScope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Equal(4, await readScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PageBeyondLast_SourceReturnsNotFound(bool purchaseOrder)
    {
        await SeedAsync(purchaseOrder, 1, 1000);
        using var client = fixture.Client(purchaseOrder ? ProcurementPermissions.PurchaseOrdersRead : ProcurementPermissions.SuppliersRead);
        using var response = await client.GetAsync($"/{(purchaseOrder ? "PurchaseOrders" : "Suppliers")}?index=2&size=1");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        if (purchaseOrder) Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
        else Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
    }

    private async Task SeedAsync(bool purchaseOrder, int count, int firstId)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        if (purchaseOrder)
        {
            var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.AddRange(Enumerable.Range(firstId, count).Select(id => new PurchaseOrder { Id = id }));
            await database.SaveChangesAsync();
        }
        else
        {
            var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            database.Suppliers.AddRange(Enumerable.Range(firstId, count).Select(id => new Supplier { Id = id, Name = $"Supplier{id}" }));
            await database.SaveChangesAsync();
        }
    }
}
