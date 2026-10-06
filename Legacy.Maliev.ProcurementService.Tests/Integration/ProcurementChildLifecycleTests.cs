using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementChildLifecycleTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task OrderItem_Lifecycle_PreservesDecimalComputationAndParentScopedLists()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.OrderItemsWrite,
            ProcurementPermissions.OrderItemsRead, ProcurementPermissions.OrderItemsDelete);
        var first = await OrderAsync(client, "First parent");
        var second = await OrderAsync(client, "Second parent");
        using var empty = await client.GetAsync($"/purchaseorders/{first.Id}/orderitems");
        Assert.Equal(HttpStatusCode.NotFound, empty.StatusCode);
        using var created = await client.PostAsJsonAsync("/purchaseorders/orderitems", new UpsertOrderItemRequest(first.Id, "PRECISION-ITEM", null, 3, 12.34m));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var item = (await created.Content.ReadFromJsonAsync<OrderItemResponse>())!;
        Assert.Equal(37.02m, item.Subtotal);
        Assert.NotNull(item.CreatedDate);
        Assert.NotNull(item.ModifiedDate);
        Assert.NotNull(created.Headers.Location);
        using var location = await client.GetAsync(created.Headers.Location);
        Assert.Equal(HttpStatusCode.OK, location.StatusCode);
        Assert.Equal(item.Id, (await location.Content.ReadFromJsonAsync<OrderItemResponse>())!.Id);
        using var wrongParent = await client.GetAsync($"/purchaseorders/{second.Id}/orderitems");
        Assert.Equal(HttpStatusCode.NotFound, wrongParent.StatusCode);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var updated = await client.PutAsJsonAsync($"/purchaseorders/orderitems/{item.Id}", new UpsertOrderItemRequest(first.Id, "PRECISION-UPDATED", "Updated description", 7, 0.01m));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var listed = Assert.Single((await client.GetFromJsonAsync<OrderItemResponse[]>($"/purchaseorders/{first.Id}/orderitems"))!);
        Assert.Equal(item.Id, listed.Id);
        Assert.Equal(first.Id, listed.PurchaseOrderId);
        Assert.Equal("PRECISION-UPDATED", listed.PartNumber);
        Assert.Equal("Updated description", listed.Description);
        Assert.Equal(7, listed.Quantity);
        Assert.Equal(0.01m, listed.UnitPrice);
        Assert.Equal(0.07m, listed.Subtotal);
        Assert.Equal(item.CreatedDate, listed.CreatedDate);
        Assert.True(listed.ModifiedDate > item.ModifiedDate);
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var stored = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().OrderItems.AsNoTracking().SingleAsync();
            Assert.Equal(0.07m, stored.Subtotal);
            Assert.Equal(first.Id, stored.PurchaseOrderId);
            Assert.Equal("PRECISION-UPDATED", stored.PartNumber);
            Assert.Equal("Updated description", stored.Description);
            Assert.Equal(7, stored.Quantity);
            Assert.Equal(0.01m, stored.UnitPrice);
        }
        using var deleted = await client.DeleteAsync($"/purchaseorders/orderitems/{item.Id}");
        using var missing = await client.GetAsync($"/purchaseorders/orderitems/{item.Id}");
        using var replay = await client.DeleteAsync($"/purchaseorders/orderitems/{item.Id}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, replay.StatusCode);
        await using var finalScope = factory.Services.CreateAsyncScope();
        Assert.Empty(await finalScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().OrderItems.ToArrayAsync());
        Assert.Equal(2, await finalScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
    }

    [Fact]
    public async Task FileMetadata_Lifecycle_ResolvesLocationAndPreservesParentScopedOwnership()
    {
        const string createdObject = "  documents/\u0e0a\u0e34\u0e49\u0e19\u0e07\u0e32\u0e19%_part drawing.pdf  ";
        const string updatedObject = " documents/\u0e0a\u0e34\u0e49\u0e19\u0e07\u0e32\u0e19%_revision.pdf ";
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.FilesWrite,
            ProcurementPermissions.FilesRead, ProcurementPermissions.FilesDelete);
        var first = await OrderAsync(client, "Metadata parent");
        var second = await OrderAsync(client, "Other parent");
        using var created = await client.PostAsync($"/purchaseorders/{first.Id}/files?bucket=owned-metadata&objectName={Uri.EscapeDataString(createdObject)}", null);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var file = (await created.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        Assert.Equal("owned-metadata", file.Bucket);
        Assert.Equal(createdObject, file.ObjectName);
        Assert.NotNull(file.CreatedDate);
        Assert.NotNull(file.ModifiedDate);
        Assert.NotNull(created.Headers.Location);
        using var location = await client.GetAsync(created.Headers.Location);
        Assert.Equal(HttpStatusCode.OK, location.StatusCode);
        var located = (await location.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        Assert.Equal(file, located);
        Assert.Equal(file, Assert.Single((await client.GetFromJsonAsync<PurchaseOrderFileResponse[]>($"/purchaseorders/{first.Id}/files"))!));
        using var emptyOther = await client.GetAsync($"/purchaseorders/{second.Id}/files");
        Assert.Equal(HttpStatusCode.NotFound, emptyOther.StatusCode);
        using var secondCreated = await client.PostAsync($"/purchaseorders/{second.Id}/files?bucket=other-metadata&objectName=unrelated.pdf", null);
        Assert.Equal(HttpStatusCode.Created, secondCreated.StatusCode);
        var unrelated = (await secondCreated.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var rows = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().ToArrayAsync();
            Assert.Equal(createdObject, Assert.Single(rows, row => row.Id == file.Id).ObjectName);
            Assert.Equal("unrelated.pdf", Assert.Single(rows, row => row.Id == unrelated.Id).ObjectName);
        }
        using var other = await client.GetAsync($"/purchaseorders/{second.Id}/files");
        Assert.Equal(HttpStatusCode.OK, other.StatusCode);
        Assert.Equal(unrelated, Assert.Single((await other.Content.ReadFromJsonAsync<PurchaseOrderFileResponse[]>())!));
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var updated = await client.PutAsJsonAsync($"/purchaseorders/files/{file.Id}", new UpsertPurchaseOrderFileRequest(first.Id, "updated-metadata", updatedObject));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var listed = Assert.Single((await client.GetFromJsonAsync<PurchaseOrderFileResponse[]>($"/purchaseorders/{first.Id}/files"))!);
        Assert.Equal(file.Id, listed.Id);
        Assert.Equal(first.Id, listed.PurchaseOrderId);
        Assert.Equal("updated-metadata", listed.Bucket);
        Assert.Equal(updatedObject, listed.ObjectName);
        Assert.Equal(listed, await client.GetFromJsonAsync<PurchaseOrderFileResponse>($"/purchaseorders/files/{file.Id}"));
        Assert.Equal(unrelated, await client.GetFromJsonAsync<PurchaseOrderFileResponse>($"/purchaseorders/files/{unrelated.Id}"));
        Assert.Equal(file.CreatedDate, listed.CreatedDate);
        Assert.True(listed.ModifiedDate > file.ModifiedDate);
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            var row = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().SingleAsync(value => value.Id == file.Id);
            Assert.Equal(file.Id, row.Id);
            Assert.Equal(first.Id, row.PurchaseOrderId);
            Assert.Equal("updated-metadata", row.Bucket);
            Assert.Equal(updatedObject, row.ObjectName);
        }
        using var deleted = await client.DeleteAsync($"/purchaseorders/files/{file.Id}");
        using var missing = await client.GetAsync($"/purchaseorders/files/{file.Id}");
        using var replay = await client.DeleteAsync($"/purchaseorders/files/{file.Id}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, replay.StatusCode);
        using var emptyAfterDelete = await client.GetAsync($"/purchaseorders/{first.Id}/files");
        Assert.Equal(HttpStatusCode.NotFound, emptyAfterDelete.StatusCode);
        await using var finalScope = factory.Services.CreateAsyncScope();
        var remaining = Assert.Single(await finalScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Files.AsNoTracking().ToArrayAsync());
        Assert.Equal(unrelated.Id, remaining.Id);
        Assert.Equal(unrelated.PurchaseOrderId, remaining.PurchaseOrderId);
        Assert.Equal(unrelated.Bucket, remaining.Bucket);
        Assert.Equal(unrelated.ObjectName, remaining.ObjectName);
        Assert.Equal(unrelated.CreatedDate, remaining.CreatedDate);
        Assert.Equal(unrelated.ModifiedDate, remaining.ModifiedDate);
        Assert.Equal(2, await finalScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().PurchaseOrders.CountAsync());
    }

    [Theory]
    [InlineData(null, "12.34", null)]
    [InlineData(2, null, null)]
    [InlineData(null, null, null)]
    [InlineData(0, "12.34", "0.00")]
    [InlineData(-2, "12.34", "-24.68")]
    public async Task OrderItem_ComputedSubtotal_PreservesSourceNullableAndSignedArithmetic(int? quantity, string? priceText, string? subtotalText)
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.OrderItemsWrite,
            ProcurementPermissions.OrderItemsRead);
        var order = await OrderAsync(client, "Computed subtotal parent");
        decimal? price = priceText is null ? null : decimal.Parse(priceText, CultureInfo.InvariantCulture);
        decimal? expected = subtotalText is null ? null : decimal.Parse(subtotalText, CultureInfo.InvariantCulture);
        var request = new UpsertOrderItemRequest(order.Id, "NULLABLE-COMPUTATION", null, quantity, price);
        using var created = await client.PostAsJsonAsync("/purchaseorders/orderitems", request);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var item = (await created.Content.ReadFromJsonAsync<OrderItemResponse>())!;
        Assert.Equal(quantity, item.Quantity);
        Assert.Equal(price, item.UnitPrice);
        Assert.Equal(expected, item.Subtotal);
        using var finite = await client.PutAsJsonAsync($"/purchaseorders/orderitems/{item.Id}", new UpsertOrderItemRequest(order.Id, "FINITE-COMPUTATION", null, 2, 3.45m));
        Assert.Equal(HttpStatusCode.NoContent, finite.StatusCode);
        Assert.Equal(6.90m, (await client.GetFromJsonAsync<OrderItemResponse>($"/purchaseorders/orderitems/{item.Id}"))!.Subtotal);
        using var restored = await client.PutAsJsonAsync($"/purchaseorders/orderitems/{item.Id}", request);
        Assert.Equal(HttpStatusCode.NoContent, restored.StatusCode);
        var current = (await client.GetFromJsonAsync<OrderItemResponse>($"/purchaseorders/orderitems/{item.Id}"))!;
        Assert.Equal(item.Id, current.Id);
        Assert.Equal(order.Id, current.PurchaseOrderId);
        Assert.Equal(quantity, current.Quantity);
        Assert.Equal(price, current.UnitPrice);
        Assert.Equal(expected, current.Subtotal);
        await using var scope = factory.Services.CreateAsyncScope();
        var row = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().OrderItems.AsNoTracking().SingleAsync();
        Assert.Equal(item.Id, row.Id);
        Assert.Equal(quantity, row.Quantity);
        Assert.Equal(price, row.UnitPrice);
        Assert.Equal(expected, row.Subtotal);
    }
    private static async Task<PurchaseOrderResponse> OrderAsync(HttpClient client, string notes)
    {
        using var response = await client.PostAsJsonAsync("/PurchaseOrders", new { Notes = notes });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
    }
}
