using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class SupplierAddressParentAuditSourceHttpTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly DateTime OriginalCreated = new(2020, 2, 3, 4, 5, 6, DateTimeKind.Unspecified);
    private static readonly DateTime OriginalModified = new(2021, 3, 4, 5, 6, 7, DateTimeKind.Unspecified);

    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task AttachOrReplace_PreservesParentDatesAndCreatesAddressWithServerDates(bool nullModified, bool replace)
    {
        await using var factory = fixture.CreateFactory(true);
        var seeded = await SeedAsync(factory.Services, nullModified, replace);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SuppliersRead);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var response = await client.PostAsJsonAsync($"/suppliers/{seeded.SupplierId}/addresses", Address("New literal address"), cancellation.Token);

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var created = (await response.Content.ReadFromJsonAsync<SupplierAddressResponse>(cancellation.Token))!;
        Assert.NotNull(response.Headers.Location);
        Assert.Equal("New literal address", created.Address1);
        var now = DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);
        Assert.Equal(now, created.CreatedDate);
        Assert.Equal(now, created.ModifiedDate);
        await AssertParentAsync(client, factory.Services, seeded.SupplierId, created.Id, nullModified, cancellation.Token);
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var stored = await database.Addresses.AsNoTracking().SingleAsync(value => value.Id == created.Id, cancellation.Token);
        Assert.Equal("New literal address", stored.Address1);
        Assert.Equal(now, stored.CreatedDate);
        Assert.Equal(now, stored.ModifiedDate);
        Assert.Equal(replace ? 2 : 1, await database.Addresses.CountAsync(cancellation.Token));
        if (seeded.AddressId is { } prior)
            Assert.Equal("Original address", (await database.Addresses.AsNoTracking().SingleAsync(value => value.Id == prior, cancellation.Token)).Address1);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DeleteCurrentAddress_PreservesParentDatesAndDetachesPointer(bool nullModified)
    {
        await using var factory = fixture.CreateFactory(true);
        var seeded = await SeedAsync(factory.Services, nullModified, attach: true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SupplierAddressesDelete, ProcurementPermissions.SuppliersRead);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var response = await client.DeleteAsync($"/suppliers/{seeded.SupplierId}/addresses/{seeded.AddressId}", cancellation.Token);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        await AssertParentAsync(client, factory.Services, seeded.SupplierId, null, nullModified, cancellation.Token);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().ToArrayAsync(cancellation.Token));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task UpdateAddress_ChangesOnlyChildAuditAndKeepsParentDates(bool nullModified)
    {
        await using var factory = fixture.CreateFactory(true);
        var seeded = await SeedAsync(factory.Services, nullModified, attach: true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SuppliersRead);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var response = await client.PutAsJsonAsync($"/suppliers/addresses/{seeded.AddressId}", Address("Updated literal address"), cancellation.Token);

        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        await AssertParentAsync(client, factory.Services, seeded.SupplierId, seeded.AddressId, nullModified, cancellation.Token);
        await using var scope = factory.Services.CreateAsyncScope();
        var child = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().SingleAsync(cancellation.Token);
        Assert.Equal("Updated literal address", child.Address1);
        Assert.Equal(OriginalCreated, child.CreatedDate);
        Assert.Equal(DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified), child.ModifiedDate);
    }

    private static async Task<(int SupplierId, int? AddressId)> SeedAsync(IServiceProvider services, bool nullModified, bool attach)
    {
        await using var scope = services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        SupplierAddress? address = attach ? new SupplierAddress
        {
            Address1 = "Original address",
            CountryId = 1,
            CreatedDate = OriginalCreated,
            ModifiedDate = OriginalModified,
        } : null;
        var supplier = new Supplier
        {
            Name = "Synthetic audit supplier",
            CreatedDate = OriginalCreated,
            ModifiedDate = OriginalModified,
            Address = address,
        };
        database.Suppliers.Add(supplier);
        await database.SaveChangesAsync();
        // A null insert would activate the schema default; seed a retained null explicitly after insertion.
        if (nullModified)
            await database.Suppliers.Where(value => value.Id == supplier.Id)
                .ExecuteUpdateAsync(setters => setters.SetProperty(value => value.ModifiedDate, (DateTime?)null));
        var stored = await database.Suppliers.AsNoTracking().SingleAsync();
        Assert.Equal(nullModified ? (DateTime?)null : OriginalModified, stored.ModifiedDate);
        Assert.Equal(OriginalCreated, stored.CreatedDate);
        return (supplier.Id, supplier.AddressId);
    }

    private static async Task AssertParentAsync(HttpClient client, IServiceProvider services, int id, int? addressId, bool nullModified, CancellationToken token)
    {
        using var response = await client.GetAsync($"/suppliers/{id}", token);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync(token);
        var value = JsonSerializer.Deserialize<SupplierResponse>(body)!;
        Assert.Equal(id, value.Id);
        Assert.Equal(addressId, value.AddressId);
        Assert.Equal(OriginalCreated, value.CreatedDate);
        Assert.Equal(nullModified ? (DateTime?)null : OriginalModified, value.ModifiedDate);
        using var json = JsonDocument.Parse(body);
        Assert.True(json.RootElement.TryGetProperty("CreatedDate", out _));
        Assert.Equal(!nullModified, json.RootElement.TryGetProperty("ModifiedDate", out _));
        Assert.False(json.RootElement.TryGetProperty("modifiedDate", out _));
        await using var scope = services.CreateAsyncScope();
        var stored = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync(token);
        Assert.Equal(id, stored.Id);
        Assert.Equal(addressId, stored.AddressId);
        Assert.Equal(OriginalCreated, stored.CreatedDate);
        Assert.Equal(nullModified ? (DateTime?)null : OriginalModified, stored.ModifiedDate);
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        Assert.Empty(await orders.Addresses.AsNoTracking().ToArrayAsync(token));
        Assert.Empty(await orders.PurchaseOrders.AsNoTracking().ToArrayAsync(token));
    }

    private static UpsertSupplierAddressRequest Address(string line) => new(null, line, null, null, null, null, 1);
}
