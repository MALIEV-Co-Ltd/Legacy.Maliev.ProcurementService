using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementAddressLifecycleTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => fixture.ResetAsync();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task SupplierAddress_CreateReadUpdate_PreservesWireShapeAndSeparateDatabase()
    {
        using var client = fixture.Client(ProcurementPermissions.SuppliersCreate,
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead);
        using var supplierResponse = await client.PostAsJsonAsync("/Suppliers", new { Name = "Address lifecycle" });
        Assert.Equal(HttpStatusCode.Created, supplierResponse.StatusCode);
        var supplier = (await supplierResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var created = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", Address("Bangkok"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        Assert.NotNull(created.Headers.Location);
        using var location = await client.GetAsync(created.Headers.Location);
        Assert.Equal(HttpStatusCode.OK, location.StatusCode);
        using var wire = JsonDocument.Parse(await location.Content.ReadAsStringAsync());
        Assert.Equal("Bangkok", wire.RootElement.GetProperty("Address1").GetString());
        Assert.False(wire.RootElement.TryGetProperty("AddressLine1", out _));
        Assert.False(wire.RootElement.TryGetProperty("Address2", out _));
        Assert.Equal(address.Id, (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/{supplier.Id}/addresses"))!.Id);
        Assert.NotNull(address.CreatedDate);
        Assert.NotNull(address.ModifiedDate);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var updated = await client.PutAsJsonAsync($"/suppliers/addresses/{address.Id}", Address("Chiang Mai"));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var current = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/{supplier.Id}/addresses"))!;
        Assert.Equal("Chiang Mai", current.Address1);
        Assert.Equal(address.CreatedDate, current.CreatedDate);
        Assert.True(current.ModifiedDate > address.ModifiedDate);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Equal(address.Id, (await database.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.Equal("Chiang Mai", (await database.Addresses.AsNoTracking().SingleAsync()).Address1);
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierAddress_MissingParentAndMissingRecords_ReturnNotFoundWithoutOrphan()
    {
        using var client = fixture.Client(ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead);
        using var create = await client.PostAsJsonAsync("/suppliers/999999/addresses", Address("Bangkok"));
        using var read = await client.GetAsync("/suppliers/addresses/999999");
        using var attached = await client.GetAsync("/suppliers/999999/addresses");
        using var update = await client.PutAsJsonAsync("/suppliers/addresses/999999", Address("Bangkok"));
        Assert.Equal(HttpStatusCode.NotFound, create.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, read.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, attached.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, update.StatusCode);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierAddress_ReadGrantCannotCreateOrUpdate_LeavesCommittedAddressIntact()
    {
        using var owner = fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SupplierAddressesWrite);
        using var supplierResponse = await owner.PostAsJsonAsync("/Suppliers", new { Name = "Permission lifecycle" });
        Assert.Equal(HttpStatusCode.Created, supplierResponse.StatusCode);
        var supplier = (await supplierResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var created = await owner.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", Address("Original"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        using var reader = fixture.Client(ProcurementPermissions.SupplierAddressesRead);
        using var deniedCreate = await reader.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", Address("Denied"));
        using var deniedUpdate = await reader.PutAsJsonAsync($"/suppliers/addresses/{address.Id}", Address("Denied"));
        Assert.Equal(HttpStatusCode.Forbidden, deniedCreate.StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, deniedUpdate.StatusCode);
        Assert.Equal("Original", (await reader.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{address.Id}"))!.Address1);
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        Assert.Single(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task PurchaseOrderAddress_ExactServiceGrant_CreateReadUpdateDelete_PreservesSeparateSchema()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrderAddressesRead, ProcurementPermissions.PurchaseOrderAddressesWrite,
            ProcurementPermissions.PurchaseOrderAddressesDelete);
        using var empty = await client.GetAsync("/purchaseorders/addresses");
        Assert.Equal(HttpStatusCode.NotFound, empty.StatusCode);
        using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", PurchaseAddress("Bangkok"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!;
        Assert.NotNull(created.Headers.Location);
        using var detail = await client.GetAsync(created.Headers.Location);
        Assert.Equal(HttpStatusCode.OK, detail.StatusCode);
        using var wire = JsonDocument.Parse(await detail.Content.ReadAsStringAsync());
        Assert.Equal("Bangkok", wire.RootElement.GetProperty("AddressLine1").GetString());
        Assert.False(wire.RootElement.TryGetProperty("Address1", out _));
        Assert.False(wire.RootElement.TryGetProperty("AddressLine2", out _));
        Assert.Equal(address.Id, Assert.Single((await client.GetFromJsonAsync<PurchaseOrderAddressResponse[]>("/purchaseorders/addresses"))!).Id);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var updated = await client.PutAsJsonAsync($"/purchaseorders/addresses/{address.Id}", PurchaseAddress("Chiang Mai"));
        Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
        var current = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{address.Id}"))!;
        Assert.Equal("Chiang Mai", current.AddressLine1);
        Assert.Equal(address.CreatedDate, current.CreatedDate);
        Assert.True(current.ModifiedDate > address.ModifiedDate);
        await using (var scope = factory.Services.CreateAsyncScope())
        {
            Assert.Equal("Chiang Mai", (await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().SingleAsync()).AddressLine1);
            Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
        }
        using var deleted = await client.DeleteAsync($"/purchaseorders/addresses/{address.Id}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        using var missing = await client.GetAsync($"/purchaseorders/addresses/{address.Id}");
        using var missingDelete = await client.DeleteAsync($"/purchaseorders/addresses/{address.Id}");
        using var missingUpdate = await client.PutAsJsonAsync($"/purchaseorders/addresses/{address.Id}", PurchaseAddress("Missing"));
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, missingDelete.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, missingUpdate.StatusCode);
        await using var finalScope = factory.Services.CreateAsyncScope();
        Assert.Empty(await finalScope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public async Task AddressWrites_BlankRequiredLine_RejectBeforePersistingEitherSchema(string? line)
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var supplierCreate = await client.PostAsJsonAsync("/suppliers/999999/addresses", Address(line));
        using var supplierUpdate = await client.PutAsJsonAsync("/suppliers/addresses/999999", Address(line));
        using var purchaseCreate = await client.PostAsJsonAsync("/purchaseorders/addresses", PurchaseAddress(line));
        using var purchaseUpdate = await client.PutAsJsonAsync("/purchaseorders/addresses/999999", PurchaseAddress(line));
        Assert.Equal(HttpStatusCode.BadRequest, supplierCreate.StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, supplierUpdate.StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, purchaseCreate.StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, purchaseUpdate.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierAddress_AuthorizedDelete_DetachesAndDeletesOnlySupplierSchema()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity", ProcurementPermissions.SuppliersCreate,
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead,
            ProcurementPermissions.SupplierAddressesDelete, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var supplierResponse = await client.PostAsJsonAsync("/Suppliers", new { Name = "Delete lifecycle" });
        Assert.Equal(HttpStatusCode.Created, supplierResponse.StatusCode);
        var supplier = (await supplierResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var created = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", Address("Supplier address"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        using var purchaseCreated = await client.PostAsJsonAsync("/purchaseorders/addresses", PurchaseAddress("Purchase address"));
        Assert.Equal(HttpStatusCode.Created, purchaseCreated.StatusCode);
        using var deleted = await client.DeleteAsync($"/suppliers/{supplier.Id}/addresses/{address.Id}");
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        using var attached = await client.GetAsync($"/suppliers/{supplier.Id}/addresses");
        using var record = await client.GetAsync($"/suppliers/addresses/{address.Id}");
        using var replay = await client.DeleteAsync($"/suppliers/{supplier.Id}/addresses/{address.Id}");
        Assert.Equal(HttpStatusCode.NotFound, attached.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, record.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, replay.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        var supplierDatabase = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        Assert.Null((await supplierDatabase.Suppliers.AsNoTracking().SingleAsync()).AddressId);
        Assert.Empty(await supplierDatabase.Addresses.ToArrayAsync());
        Assert.Equal("Purchase address", (await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().SingleAsync()).AddressLine1);
    }

    [Theory]
    [InlineData(false, "service:procurement-parity")]
    [InlineData(true, "employee:procurement-parity")]
    public async Task PurchaseOrderAddress_LiveWriteWithoutTrustedServiceOptIn_DoesNotPersist(bool optIn, string subject)
    {
        await using var factory = fixture.CreateFactory(optIn);
        using var client = fixture.ClientAs(factory, subject, ProcurementPermissions.PurchaseOrderAddressesWrite);
        using var response = await client.PostAsJsonAsync("/purchaseorders/addresses", PurchaseAddress("Denied"));
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.ToArrayAsync());
        Assert.Empty(await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task PurchaseOrderAddress_InUseDelete_RealForeignKeyPreservesOrderAndAddress()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesDelete,
            ProcurementPermissions.PurchaseOrderAddressesRead, ProcurementPermissions.PurchaseOrdersCreate);
        using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", PurchaseAddress("Referenced address"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var address = (await created.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!;
        using var orderResponse = await client.PostAsJsonAsync("/PurchaseOrders", new { ShippingAddressId = address.Id, BillingAddressId = address.Id });
        Assert.Equal(HttpStatusCode.Created, orderResponse.StatusCode);
        var order = (await orderResponse.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
        using var deleted = await client.DeleteAsync($"/purchaseorders/addresses/{address.Id}");
        Assert.Equal(HttpStatusCode.InternalServerError, deleted.StatusCode);
        var error = await deleted.Content.ReadAsStringAsync();
        Assert.DoesNotContain("Npgsql", error, StringComparison.Ordinal);
        Assert.DoesNotContain("Referenced address", error, StringComparison.Ordinal);
        Assert.Equal(address.Id, (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{address.Id}"))!.Id);
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var stored = await database.PurchaseOrders.AsNoTracking().SingleAsync();
        Assert.Equal(order.Id, stored.Id);
        Assert.Equal(address.Id, stored.ShippingAddressId);
        Assert.Equal(address.Id, stored.BillingAddressId);
        Assert.Single(await database.Addresses.ToArrayAsync());
    }

    [Fact]
    public async Task SupplierAddress_WrongOwnerDelete_CurrentSecurityPolicyPreservesBothAttachments()
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SupplierAddressesWrite,
            ProcurementPermissions.SupplierAddressesRead, ProcurementPermissions.SupplierAddressesDelete);
        using var firstResponse = await client.PostAsJsonAsync("/Suppliers", new { Name = "First owner" });
        using var secondResponse = await client.PostAsJsonAsync("/Suppliers", new { Name = "Second owner" });
        Assert.Equal(HttpStatusCode.Created, firstResponse.StatusCode);
        Assert.Equal(HttpStatusCode.Created, secondResponse.StatusCode);
        var first = (await firstResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
        var second = (await secondResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
        using var firstAddressResponse = await client.PostAsJsonAsync($"/suppliers/{first.Id}/addresses", Address("First attachment"));
        using var secondAddressResponse = await client.PostAsJsonAsync($"/suppliers/{second.Id}/addresses", Address("Second attachment"));
        Assert.Equal(HttpStatusCode.Created, firstAddressResponse.StatusCode);
        Assert.Equal(HttpStatusCode.Created, secondAddressResponse.StatusCode);
        var firstAddress = (await firstAddressResponse.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        var secondAddress = (await secondAddressResponse.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        using var deleted = await client.DeleteAsync($"/suppliers/{second.Id}/addresses/{firstAddress.Id}");
        Assert.Equal(HttpStatusCode.NotFound, deleted.StatusCode);
        Assert.Equal(firstAddress.Id, (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/{first.Id}/addresses"))!.Id);
        Assert.Equal(secondAddress.Id, (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/{second.Id}/addresses"))!.Id);
        await using var scope = factory.Services.CreateAsyncScope();
        Assert.Equal(2, await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.CountAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AddressWrites_PopulatedFields_SurviveCreateAndUpdate(bool purchaseOrder)
    {
        await using var factory = fixture.CreateFactory(true);
        using var client = fixture.ClientAs(factory, "service:procurement-parity",
            ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SupplierAddressesRead,
            ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead,
            ProcurementPermissions.PurchaseOrderAddressesWrite);
        if (purchaseOrder)
        {
            var input = new UpsertPurchaseOrderAddressRequest("Tower A", "First road", "Floor 2", "Bangkok", "Bangkok", "10110", 1);
            using var created = await client.PostAsJsonAsync("/purchaseorders/addresses", input);
            Assert.Equal(HttpStatusCode.Created, created.StatusCode);
            var address = (await created.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!;
            Assert.Equal(input, new UpsertPurchaseOrderAddressRequest(address.Building, address.AddressLine1, address.AddressLine2, address.City, address.State, address.PostalCode, address.CountryId));
            var changed = new UpsertPurchaseOrderAddressRequest("Tower B", "Second road", "Floor 3", "Chiang Mai", "Chiang Mai", "50000", 2);
            using var updated = await client.PutAsJsonAsync($"/purchaseorders/addresses/{address.Id}", changed);
            Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
            var current = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{address.Id}"))!;
            Assert.Equal(changed, new UpsertPurchaseOrderAddressRequest(current.Building, current.AddressLine1, current.AddressLine2, current.City, current.State, current.PostalCode, current.CountryId));
            await using var scope = factory.Services.CreateAsyncScope();
            var stored = await scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>().Addresses.AsNoTracking().SingleAsync();
            Assert.Equal(changed, new UpsertPurchaseOrderAddressRequest(stored.Building, stored.AddressLine1, stored.AddressLine2, stored.City, stored.State, stored.PostalCode, stored.CountryId));
        }
        else
        {
            using var supplierResponse = await client.PostAsJsonAsync("/Suppliers", new { Name = "Populated address" });
            Assert.Equal(HttpStatusCode.Created, supplierResponse.StatusCode);
            var supplier = (await supplierResponse.Content.ReadFromJsonAsync<SupplierResponse>())!;
            var input = new UpsertSupplierAddressRequest("Tower A", "First road", "Floor 2", "Bangkok", "Bangkok", "10110", 1);
            using var created = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", input);
            Assert.Equal(HttpStatusCode.Created, created.StatusCode);
            var address = (await created.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
            Assert.Equal(input, new UpsertSupplierAddressRequest(address.Building, address.Address1, address.Address2, address.City, address.State, address.PostalCode, address.CountryId));
            var changed = new UpsertSupplierAddressRequest("Tower B", "Second road", "Floor 3", "Chiang Mai", "Chiang Mai", "50000", 2);
            using var updated = await client.PutAsJsonAsync($"/suppliers/addresses/{address.Id}", changed);
            Assert.Equal(HttpStatusCode.NoContent, updated.StatusCode);
            var current = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{address.Id}"))!;
            Assert.Equal(changed, new UpsertSupplierAddressRequest(current.Building, current.Address1, current.Address2, current.City, current.State, current.PostalCode, current.CountryId));
            await using var scope = factory.Services.CreateAsyncScope();
            var stored = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Addresses.AsNoTracking().SingleAsync();
            Assert.Equal(changed, new UpsertSupplierAddressRequest(stored.Building, stored.Address1, stored.Address2, stored.City, stored.State, stored.PostalCode, stored.CountryId));
        }
    }
    private static UpsertPurchaseOrderAddressRequest PurchaseAddress(string? line) => new(null, line!, null, null, null, null, 1);
    private static UpsertSupplierAddressRequest Address(string? line) => new(null, line, null, null, null, null, 1);
}
