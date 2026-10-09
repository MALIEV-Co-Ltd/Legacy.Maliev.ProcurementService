using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementIndependentContactTests(ProcurementRuntimeFixture<ProcurementIndependentContactTests> fixture)
    : IClassFixture<ProcurementRuntimeFixture<ProcurementIndependentContactTests>>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData("Supplier Thai ผู้ขาย ", "Shipping Thai ผู้รับ ")]
    [InlineData(null, "Shipping only")]
    [InlineData("Supplier only", null)]
    [InlineData("", " ")]
    public async Task PostAndPutPreserveIndependentContactsThroughFreshReads(string? supplier, string? shipping)
    {
        using var client = fixture.Client(ProcurementPermissions.PurchaseOrdersCreate,
            ProcurementPermissions.PurchaseOrdersUpdate, ProcurementPermissions.PurchaseOrdersRead);
        var request = Request(supplier, shipping);
        using var created = await client.PostAsJsonAsync("/PurchaseOrders", request);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var response = (await created.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
        Assert.Equal(supplier, response.SupplierContactPerson);
        Assert.Equal(shipping, response.ShippingContactPerson);
        await AssertRetainedAsync(response.Id, supplier, shipping);

        // Swap distinct values so a no-op PUT or cross-field assignment cannot pass.
        using var updated = await client.PutAsJsonAsync($"/PurchaseOrders/{response.Id}", Request(shipping, supplier));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        await AssertRetainedAsync(response.Id, shipping, supplier);

        async Task AssertRetainedAsync(int id, string? expectedSupplier, string? expectedShipping)
        {
            var fresh = (await client.GetFromJsonAsync<PurchaseOrderResponse>($"/PurchaseOrders/{id}"))!;
            Assert.Equal(expectedSupplier, fresh.SupplierContactPerson);
            Assert.Equal(expectedShipping, fresh.ShippingContactPerson);
            await using var scope = fixture.Factory.Services.CreateAsyncScope();
            var row = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>()
                .PurchaseOrders.AsNoTracking().SingleAsync(value => value.Id == id);
            Assert.Equal(expectedSupplier, row.SupplierContactPerson);
            Assert.Equal(expectedShipping, row.ShippingContactPerson);
            Assert.Equal(1, await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
        }
    }

    private static UpsertPurchaseOrderRequest Request(string? supplier, string? shipping) =>
        new(SupplierId: null, SupplierContactPerson: supplier, ShippingAddressId: null, ShippingContactPerson: shipping,
            ShippingTelephone: null, ShippingMobile: null, ShippingFax: null, BillingAddressId: null,
            BillingContactPerson: null, BillingTelephone: null, BillingMobile: null, BillingFax: null,
            Fob: null, Terms: null, ShippingMethod: null, EmployeeId: null, Notes: null);
}
