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

public sealed class ProcurementSupplierIgnoredIdTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Addresses.Add(new SupplierAddress { Id = 7001, Address1 = "Sentinel address", CountryId = 1 });
        suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "Sentinel supplier", AddressId = 7001 });
        await suppliers.SaveChangesAsync();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.Addresses.Add(new PurchaseOrderAddress { Id = 7003, AddressLine1 = "Sentinel PO address", CountryId = 1 });
        orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003 });
        orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "Sentinel part" });
        orders.Files.Add(new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "sentinel", ObjectName = "metadata-only" });
        await orders.SaveChangesAsync();
    }

    public Task DisposeAsync() => Task.CompletedTask;

    public static TheoryData<bool, string> ValidIds
    {
        get
        {
            var cases = new TheoryData<bool, string>();
            foreach (var update in new[] { false, true })
                foreach (var token in new[] { "0", "-17", "2147483647", "-2147483648", "\"42\"", "\" +42 \"", "\"\"", "null", "123" })
                    cases.Add(update, token);
            return cases;
        }
    }

    public static TheoryData<bool, string> InvalidIds
    {
        get
        {
            var cases = new TheoryData<bool, string>();
            foreach (var update in new[] { false, true })
                foreach (var token in new[] { "1.5", "1e3", "true", "false", "[]", "{}", "2147483648", "-2147483649", "\"nope\"", "\"1.0\"", "\"2147483648\"", "\"null\"" })
                    cases.Add(update, token);
            return cases;
        }
    }

    [Theory]
    [MemberData(nameof(ValidIds))]
    public async Task ValidBodyId_IsDiscardedAndServerIdentityAndGraphArePreserved(bool update, string token)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var before = await SnapshotAsync(update ? id : null);
        var original = update ? await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}") : null;
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, id, "\"iD\":" + token + ",");
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update)
        {
            var created = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!;
            id = created.Id;
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<SupplierResponse>())!.Id);
        }
        Assert.InRange(id, 1, 100);
        using var fresh = await client.GetAsync($"/Suppliers/{id}");
        using var document = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        Assert.Equal(JsonValueKind.Number, document.RootElement.GetProperty("Id").ValueKind);
        var current = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
        Assert.Equal("ชื่อไทย", current.Name);
        Assert.Equal("12.3400E+03", current.Website);
        Assert.Equal("true", current.Telephone);
        if (update)
        {
            Assert.Equal(original!.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
            Assert.Equal(7001, current.AddressId);
        }
        else
        {
            Assert.Equal(fixture.Clock.GetUtcNow().UtcDateTime, current.CreatedDate);
            Assert.Equal(current.CreatedDate, current.ModifiedDate);
            Assert.Null(current.AddressId);
        }
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.Equal(current.Name, row.Name);
        Assert.Equal(current.Website, row.Website);
        Assert.Equal(current.Telephone, row.Telephone);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(2, await suppliers.Suppliers.CountAsync());
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [MemberData(nameof(InvalidIds))]
    public async Task MalformedBodyId_IsBadRequestWithoutAnyStoredChange(bool update, string token)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, id, "\"Id\":" + token + ",");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, "\"Id\":{},\"id\":1,", false)]
    [InlineData(true, "\"Id\":{},\"id\":1,", false)]
    [InlineData(false, "\"Id\":1,\"id\":{},", false)]
    [InlineData(true, "\"Id\":1,\"id\":{},", false)]
    [InlineData(false, "\"Id\":2147483647,\"id\":null,", true)]
    [InlineData(true, "\"Id\":2147483647,\"id\":null,", true)]
    public async Task EveryDuplicateId_IsValidatedBeforeDiscard(bool update, string members, bool accepted)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var before = await SnapshotAsync(accepted && update ? id : null);
        using var response = await SendAsync(client, update, id, members);
        Assert.Equal(accepted ? (update ? HttpStatusCode.NoContent : HttpStatusCode.Created) : HttpStatusCode.BadRequest, response.StatusCode);
        if (!accepted) Assert.Equal(before, await SnapshotAsync());
        else
        {
            if (!update) id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
            Assert.InRange(id, 1, 100);
            Assert.Equal(before, await SnapshotAsync(id));
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OmittedIdAndUnknownMembers_KeepExistingRequestShape(bool update)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        using var response = await SendAsync(client, update, id, "\"Unrelated\":{\"Id\":{}},");
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        Assert.DoesNotContain(typeof(UpsertSupplierRequest).GetProperties(), property => property.Name == "Id");
        Assert.Equal(8, typeof(UpsertSupplierRequest).GetProperties().Length);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, true)]
    [InlineData(false, false)]
    [InlineData(true, false)]
    public async Task AuthenticationAndPermissionStillPrecedeBodyBinding(bool update, bool anonymous)
    {
        using var owner = Writer();
        var id = update ? await CreateControlAsync(owner) : 0;
        using var client = anonymous ? fixture.Factory.CreateClient() : fixture.Client(ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, id, "\"Id\":{},");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public void MvcConverter_IsRequestOnlyAndKeepsEightPropertyWriteShape()
    {
        using var scope = fixture.Factory.Services.CreateScope();
        var options = scope.ServiceProvider.GetRequiredService<Microsoft.Extensions.Options.IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;
        Assert.Equal("SupplierIgnoredIdJsonConverter", options.GetConverter(typeof(UpsertSupplierRequest)).GetType().Name);
        Assert.NotEqual("SupplierIgnoredIdJsonConverter", options.GetConverter(typeof(SupplierResponse)).GetType().Name);
        Assert.NotEqual("SupplierIgnoredIdJsonConverter", options.GetConverter(typeof(UpsertPurchaseOrderRequest)).GetType().Name);
        var request = new UpsertSupplierRequest("Name", "Website", "Tax", "Email", "Note", "Telephone", "Mobile", "Fax");
        var text = JsonSerializer.Serialize(request, options);
        using var document = JsonDocument.Parse(text);
        Assert.Equal(8, document.RootElement.EnumerateObject().Count());
        Assert.False(document.RootElement.TryGetProperty("Id", out _));
        Assert.Equal(request, JsonSerializer.Deserialize<UpsertSupplierRequest>(text, options));
    }

    private HttpClient Writer() => fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead);

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string members)
    {
        using var content = new StringContent("{" + members + "\"Name\":\"ชื่อไทย\",\"Website\":12.3400E+03,\"Telephone\":true}", Encoding.UTF8, "application/json");
        return update ? await client.PutAsync($"/Suppliers/{id}", content) : await client.PostAsync("/Suppliers", content);
    }

    private static async Task<int> CreateControlAsync(HttpClient client)
    {
        using var response = await client.PostAsJsonAsync("/Suppliers", new UpsertSupplierRequest("Control", null, null, null, null, null, null, null));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var context = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await context.Suppliers.SingleAsync(value => value.Id == id);
        row.AddressId = 7001;
        await context.SaveChangesAsync();
        return id;
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
