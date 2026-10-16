using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementSupplierIgnoredAddressIdTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Addresses.AddRange(
            new SupplierAddress { Id = 7001, Address1 = "First owner's address", CountryId = 1 },
            new SupplierAddress { Id = 7007, Address1 = "Second owner's address", CountryId = 1 });
        suppliers.Suppliers.AddRange(
            new Supplier { Id = 7002, Name = "First owner", AddressId = 7001 },
            new Supplier { Id = 7008, Name = "Second owner", AddressId = 7007 });
        await suppliers.SaveChangesAsync();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.Addresses.Add(new PurchaseOrderAddress { Id = 7010, AddressLine1 = "PO address", CountryId = 1 });
        orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7011, SupplierId = 7002, ShippingAddressId = 7010, BillingAddressId = 7010 });
        orders.OrderItems.Add(new OrderItem { Id = 7012, PurchaseOrderId = 7011, PartNumber = "Sentinel part" });
        orders.Files.Add(new PurchaseOrderFile { Id = 7013, PurchaseOrderId = 7011, Bucket = "sentinel", ObjectName = "metadata-only" });
        await orders.SaveChangesAsync();
    }

    public Task DisposeAsync() => Task.CompletedTask;

    public static TheoryData<bool, string> ValidAddressIds
    {
        get
        {
            var cases = new TheoryData<bool, string>();
            foreach (var update in new[] { false, true })
                foreach (var token in new[] { "0", "7001", "7007", "9000", "-17", "2147483647", "-2147483648", "\"7007\"", "\" +7007 \"", "\"\"", "null" })
                    cases.Add(update, token);
            return cases;
        }
    }

    public static TheoryData<bool, string> InvalidAddressIds
    {
        get
        {
            var cases = new TheoryData<bool, string>();
            foreach (var update in new[] { false, true })
                foreach (var token in new[] { "1.5", "1e3", "true", "{}", "[]", "2147483648", "-2147483649", "\"nope\"", "\"2147483648\"" })
                    cases.Add(update, token);
            return cases;
        }
    }

    [Theory]
    [MemberData(nameof(ValidAddressIds))]
    public async Task ValidBodyAddressId_CannotAttachReplaceOrClearTheOwnedLink(bool update, string token)
    {
        using var client = Writer();
        var original = update ? await CreateLinkedControlAsync(client) : null;
        var id = original?.Id ?? 0;
        var before = await SnapshotAsync(update ? id : null);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, id, "\"aDdReSsId\":" + token + ",");
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update)
        {
            var created = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!;
            Assert.Null(created.AddressId);
            id = created.Id;
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<SupplierResponse>())!.Id);
        }
        var current = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
        Assert.InRange(current.Id, 1, 100);
        Assert.Equal(original?.AddressId, current.AddressId);
        Assert.Equal("ชื่อไทย", current.Name);
        Assert.Equal("12.3400E+03", current.Website);
        Assert.Equal("true", current.Telephone);
        Assert.Null(current.Note);
        if (update)
        {
            Assert.Equal(original!.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
        }
        else
        {
            Assert.Equal(fixture.Clock.GetUtcNow().UtcDateTime, current.CreatedDate);
            Assert.Equal(current.CreatedDate, current.ModifiedDate);
        }
        using var addressReader = fixture.Client(ProcurementPermissions.SupplierAddressesRead);
        using var attached = await addressReader.GetAsync($"/suppliers/{id}/addresses");
        Assert.Equal(update ? HttpStatusCode.OK : HttpStatusCode.NotFound, attached.StatusCode);
        if (update)
        {
            var address = (await attached.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
            Assert.Equal(original!.AddressId, address.Id);
            Assert.Equal("Control address", address.Address1);
        }
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.Equal(current.AddressId, row.AddressId);
        Assert.Equal(current.Name, row.Name);
        Assert.Equal(current.Website, row.Website);
        Assert.Equal(current.Telephone, row.Telephone);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(3, await suppliers.Suppliers.CountAsync());
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [MemberData(nameof(InvalidAddressIds))]
    public async Task MalformedBodyAddressId_IsRejectedBeforeAnyStoredWrite(bool update, string token)
    {
        using var client = Writer();
        var original = update ? await CreateLinkedControlAsync(client) : null;
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, original?.Id ?? 0, "\"AddressId\":" + token + ",");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, "\"AddressId\":{},\"addressid\":7007,", false)]
    [InlineData(true, "\"AddressId\":{},\"addressid\":7007,", false)]
    [InlineData(false, "\"AddressId\":7007,\"addressid\":{},", false)]
    [InlineData(true, "\"AddressId\":7007,\"addressid\":{},", false)]
    [InlineData(false, "\"AddressId\":7007,\"addressid\":null,", true)]
    [InlineData(true, "\"AddressId\":7007,\"addressid\":null,", true)]
    public async Task EveryDuplicateAddressId_IsValidatedThenDiscarded(bool update, string members, bool accepted)
    {
        using var client = Writer();
        var original = update ? await CreateLinkedControlAsync(client) : null;
        var id = original?.Id ?? 0;
        var before = await SnapshotAsync(accepted && update ? id : null);
        using var response = await SendAsync(client, update, id, members);
        Assert.Equal(accepted ? (update ? HttpStatusCode.NoContent : HttpStatusCode.Created) : HttpStatusCode.BadRequest, response.StatusCode);
        if (!accepted) Assert.Equal(before, await SnapshotAsync());
        else
        {
            if (!update) id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
            var current = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
            Assert.Equal(original?.AddressId, current.AddressId);
            Assert.Equal(before, await SnapshotAsync(id));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OmittedAddressId_RemainsAbsentFromTheEightFieldRequest(bool update)
    {
        using var client = Writer();
        var original = update ? await CreateLinkedControlAsync(client) : null;
        var id = original?.Id ?? 0;
        using var response = await SendAsync(client, update, id, "\"Unrelated\":{\"AddressId\":{}},");
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update) id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        Assert.Equal(original?.AddressId, (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!.AddressId);
        Assert.Equal(8, typeof(UpsertSupplierRequest).GetProperties().Length);
        Assert.DoesNotContain(typeof(UpsertSupplierRequest).GetProperties(), property => property.Name == "AddressId");
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, true)]
    [InlineData(false, false)]
    [InlineData(true, false)]
    public async Task AuthenticationAndPermissionStillPrecedeAddressIdBinding(bool update, bool anonymous)
    {
        using var owner = Writer();
        var original = update ? await CreateLinkedControlAsync(owner) : null;
        using var client = anonymous ? fixture.Factory.CreateClient() : fixture.Client(ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, original?.Id ?? 0, "\"AddressId\":{},");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    private HttpClient Writer() => fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead);

    private async Task<SupplierResponse> CreateLinkedControlAsync(HttpClient client)
    {
        using var response = await client.PostAsJsonAsync("/Suppliers", new UpsertSupplierRequest("Control", null, null, null, null, null, null, null));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        using var addressWriter = fixture.Client(ProcurementPermissions.SupplierAddressesWrite);
        using var address = await addressWriter.PostAsJsonAsync($"/suppliers/{id}/addresses", new UpsertSupplierAddressRequest(null, "Control address", null, null, null, null, 1));
        Assert.Equal(HttpStatusCode.Created, address.StatusCode);
        return (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
    }

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string members)
    {
        using var content = new StringContent("{" + members + "\"Name\":\"ชื่อไทย\",\"Website\":12.3400E+03,\"Telephone\":true}", Encoding.UTF8, "application/json");
        return update ? await client.PutAsync($"/Suppliers/{id}", content) : await client.PostAsync("/Suppliers", content);
    }

    private async Task<string> SnapshotAsync(int? excludedSupplierId = null)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().Where(value => excludedSupplierId == null || value.Id != excludedSupplierId).OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrderAddresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            OrderItems = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }
}
