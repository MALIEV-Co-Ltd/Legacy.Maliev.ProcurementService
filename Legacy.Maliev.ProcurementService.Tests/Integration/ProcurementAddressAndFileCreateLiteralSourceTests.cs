using System.Net;
using System.Net.Http.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementAddressAndFileCreateLiteralSourceTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("  ไทย  ")]
    public async Task PurchaseOrderAddressJsonPostAndPutCopyValidLiteralsAndZeroCountryExactly(string literal)
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead);
        using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", Address(literal));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!;
        Assert.Equal(literal, address.AddressLine1);
        Assert.Equal(0, address.CountryId);
        Assert.Equal(literal, (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{address.Id}"))!.AddressLine1);
        string updatedLiteral = literal + " ";
        using var updated = await client.PutAsJsonAsync($"/purchaseorders/addresses/{address.Id}", Address(updatedLiteral));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var fresh = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{address.Id}"))!;
        Assert.Equal(updatedLiteral, fresh.AddressLine1);
        Assert.Equal(0, fresh.CountryId);
        await using var scope = factory.Services.CreateAsyncScope();
        var stored = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().SingleAsync();
        Assert.Equal(updatedLiteral, stored.AddressLine1);
        Assert.Equal(0, stored.CountryId);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FilePostKeepsPaddedNonEmptyBucketAndDefaultBindingRejectsAllSpace(bool allSpace)
    {
        await using var factory = fixture.CreateFactory(true);
        await using (var seed = factory.Services.CreateAsyncScope())
        {
            var database = seed.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            database.PurchaseOrders.Add(new PurchaseOrder { Id = 93 });
            await database.SaveChangesAsync();
        }
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);
        string bucket = allSpace ? "   " : "  synthetic-bucket  ";
        const string objectName = " drawings/ไทย.dwg ";
        using var created = await client.PostAsync($"/purchaseorders/93/files?bucket={Uri.EscapeDataString(bucket)}&objectName={Uri.EscapeDataString(objectName)}", null);
        Assert.Equal(allSpace ? HttpStatusCode.BadRequest : HttpStatusCode.Created, created.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        var databaseRead = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        if (allSpace)
            Assert.Empty(await databaseRead.Files.ToArrayAsync());
        else
        {
            var file = (await created.Content.ReadFromJsonAsync<PurchaseOrderFileResponse>())!;
            var fresh = (await client.GetFromJsonAsync<PurchaseOrderFileResponse>($"/purchaseorders/files/{file.Id}"))!;
            Assert.Equal(bucket, fresh.Bucket);
            Assert.Equal(objectName, fresh.ObjectName);
            var stored = await databaseRead.Files.AsNoTracking().SingleAsync();
            Assert.Equal(bucket, stored.Bucket);
            Assert.Equal(objectName, stored.ObjectName);
            Assert.Equal(93, stored.PurchaseOrderId);
        }
        Assert.Single(await databaseRead.PurchaseOrders.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.ToArrayAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingWritePermissionCannotPersistEitherLiteralRoute(bool file)
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            file ? ProcurementPermissions.FilesRead : ProcurementPermissions.PurchaseOrderAddressesRead);
        using var response = file
            ? await client.PostAsync("/purchaseorders/93/files?bucket=synthetic&objectName=synthetic", null)
            : await client.PostAsJsonAsync("/purchaseorders/addresses", Address("  ไทย  "));
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        Assert.Empty(await orders.Files.ToArrayAsync());
        Assert.Empty(await orders.Addresses.ToArrayAsync());
        Assert.Empty(await orders.PurchaseOrders.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
    }

    private static UpsertPurchaseOrderAddressRequest Address(string literal) => new(null, literal, null, null, null, null, 0);
}
