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

public sealed class ProcurementPurchaseOrderAddressScalarStringTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] Fields = ["Building", "AddressLine1", "AddressLine2", "City", "State", "PostalCode"];

    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Addresses.Add(new SupplierAddress { Id = 80, Address1 = "Unrelated supplier address", CountryId = 7 });
        suppliers.Suppliers.Add(new Supplier { Id = 80, Name = "Unrelated supplier", AddressId = 80 });
        await suppliers.SaveChangesAsync();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.Addresses.Add(new PurchaseOrderAddress { Id = 80, AddressLine1 = "Unrelated PO address", CountryId = 7 });
        orders.PurchaseOrders.Add(new PurchaseOrder { Id = 80, SupplierId = 80, ShippingAddressId = 80, BillingAddressId = 80 });
        orders.OrderItems.Add(new OrderItem { Id = 80, PurchaseOrderId = 80 });
        orders.Files.Add(new PurchaseOrderFile { Id = 80, PurchaseOrderId = 80, Bucket = "synthetic", ObjectName = "metadata-only" });
        await orders.SaveChangesAsync();
    }

    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData(false, "123", "123")]
    [InlineData(true, "123", "123")]
    [InlineData(false, "-0", "-0")]
    [InlineData(true, "-0", "-0")]
    [InlineData(false, "1.2300E+03", "1.2300E+03")]
    [InlineData(true, "1.2300E+03", "1.2300E+03")]
    [InlineData(false, "true", "true")]
    [InlineData(true, "true", "true")]
    [InlineData(false, "false", "false")]
    [InlineData(true, "false", "false")]
    [InlineData(false, "\"  ไทย  \"", "  ไทย  ")]
    [InlineData(true, "\"  ไทย  \"", "  ไทย  ")]
    [InlineData(false, "\"Literal.CASE\"", "Literal.CASE")]
    [InlineData(true, "\"Literal.CASE\"", "Literal.CASE")]
    public async Task PostAndPut_SourcePrimitiveAddressFields_PersistExactStrings(bool update, string token, string expected)
    {
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync(original?.Id);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, original?.Id ?? 0, Payload(token));
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!.Id;
        if (!update)
        {
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!.Id);
        }
        using var fresh = await client.GetAsync($"/purchaseorders/addresses/{id}");
        Assert.Equal(HttpStatusCode.OK, fresh.StatusCode);
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        foreach (var field in Fields)
        {
            Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty(field).ValueKind);
            Assert.Equal(expected, wire.RootElement.GetProperty(field).GetString());
        }
        Assert.Equal(JsonValueKind.Number, wire.RootElement.GetProperty("CountryId").ValueKind);
        Assert.Equal(7, wire.RootElement.GetProperty("CountryId").GetInt32());
        Assert.False(wire.RootElement.TryGetProperty("Address1", out _));
        var current = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{id}"))!;
        Assert.Equal(Enumerable.Repeat(expected, Fields.Length), Text(current));
        if (original is not null) Assert.Equal(original.CreatedDate, current.CreatedDate);
        else Assert.Equal(current.CreatedDate, current.ModifiedDate);
        Assert.NotNull(current.CreatedDate);
        if (original is not null) Assert.True(current.ModifiedDate > original.ModifiedDate);
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task OptionalFields_NullOrOmitted_RemainNullable(bool update, bool omitted)
    {
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync(original?.Id);
        var body = "{\"AddressLine1\":\"Required line\",\"CountryId\":7" + (omitted ? "}" : "," + string.Join(",", Fields.Where(field => field != "AddressLine1").Select(field => $"\"{field}\":null")) + "}");
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, original?.Id ?? 0, body);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!.Id;
        var current = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{id}"))!;
        Assert.Equal(new string?[] { null, "Required line", null, null, null, null }, Text(current));
        using var fresh = await client.GetAsync($"/purchaseorders/addresses/{id}");
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        foreach (var field in Fields.Where(field => field != "AddressLine1")) Assert.False(wire.RootElement.TryGetProperty(field, out _));
        if (original is not null) Assert.Equal(original.CreatedDate, current.CreatedDate);
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData("Building")]
    [InlineData("AddressLine1")]
    [InlineData("AddressLine2")]
    [InlineData("City")]
    [InlineData("State")]
    [InlineData("PostalCode")]
    public async Task EveryTextProperty_RejectsObjectAndArray_WithoutWrites(string field)
    {
        using var client = Writer();
        var original = await PrepareAsync(client);
        var before = await SnapshotAsync();
        foreach (var update in new[] { false, true })
            foreach (var nested in new[] { "[]", "{}" })
            {
                var body = "{" + string.Join(",", Fields.Select(value => $"\"{value}\":{(value == field ? nested : "\"Valid\"")}")) + ",\"CountryId\":7}";
                using var response = await SendAsync(client, update, original.Id, body);
                Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
                Assert.Equal(before, await SnapshotAsync());
            }
    }

    [Fact]
    public async Task MissingAddress_WithScalarText_ReachesNotFoundWithoutWrites()
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, true, 999999, Payload("true"));
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task NullRequiredLine_CurrentGuardRejectsWithoutWrites(bool update)
    {
        using var client = Writer();
        var original = await PrepareAsync(client);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, original.Id, Payload("null"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task EmptyTextAndZeroCountry_PreserveLiteralBehavior(bool update)
    {
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync(original?.Id);
        using var response = await SendAsync(client, update, original?.Id ?? 0, Payload("\"\"").Replace("\"CountryId\":7", "\"CountryId\":0", StringComparison.Ordinal));
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!.Id;
        var current = (await client.GetFromJsonAsync<PurchaseOrderAddressResponse>($"/purchaseorders/addresses/{id}"))!;
        Assert.Equal(Enumerable.Repeat("", Fields.Length), Text(current));
        Assert.Equal(0, current.CountryId);
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingWritePermission_CannotPersistScalarAddress(bool authenticated)
    {
        using var client = authenticated ? fixture.Client(ProcurementPermissions.PurchaseOrderAddressesRead) : fixture.Factory.CreateClient();
        using var writer = Writer();
        var original = await PrepareAsync(writer);
        var before = await SnapshotAsync();
        foreach (var update in new[] { false, true })
        {
            using var response = await SendAsync(client, update, original.Id, Payload("123"));
            Assert.Equal(authenticated ? HttpStatusCode.Forbidden : HttpStatusCode.Unauthorized, response.StatusCode);
            Assert.Equal(before, await SnapshotAsync());
        }
    }

    [Fact]
    public void Converter_IsPurchaseOrderAddressLocal_AndWritesStrings()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Notes\":123}"));
        var request = JsonSerializer.Deserialize<UpsertPurchaseOrderAddressRequest>(Payload("1.2300E+03"))!;
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(request));
        foreach (var field in Fields) Assert.Equal("1.2300E+03", wire.RootElement.GetProperty(field).GetString());
        Assert.Equal(7, wire.RootElement.GetProperty("CountryId").GetInt32());
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderAddressRequest>("{\"AddressLine1\":\"Valid\",\"CountryId\":true}"));
    }

    private HttpClient Writer() => fixture.Client(ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead);
    private static string Payload(string token) => "{" + string.Join(",", Fields.Select(field => $"\"{field}\":{token}")) + ",\"CountryId\":7}";
    private static string?[] Text(PurchaseOrderAddressResponse value) => [value.Building, value.AddressLine1, value.AddressLine2, value.City, value.State, value.PostalCode];
    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string body)
    {
        using var content = new StringContent(body, Encoding.UTF8, "application/json");
        return update ? await client.PutAsync($"/purchaseorders/addresses/{id}", content) : await client.PostAsync("/purchaseorders/addresses", content);
    }
    private static async Task<PurchaseOrderAddressResponse> PrepareAsync(HttpClient client)
    {
        using var response = await client.PostAsJsonAsync("/purchaseorders/addresses", new UpsertPurchaseOrderAddressRequest("Original", "Original", "Original", "Original", "Original", "Original", 7));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<PurchaseOrderAddressResponse>())!;
    }
    private async Task VerifyRowAsync(PurchaseOrderAddressResponse current)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var row = await orders.Addresses.AsNoTracking().SingleAsync(value => value.Id == current.Id);
        Assert.Equal(Text(current), new string?[] { row.Building, row.AddressLine1, row.AddressLine2, row.City, row.State, row.PostalCode });
        Assert.Equal(current.CountryId, row.CountryId);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(2, await orders.Addresses.CountAsync());
    }
    private async Task<string> SnapshotAsync(int? excludedAddressId = null)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrderAddresses = await orders.Addresses.AsNoTracking().Where(value => excludedAddressId == null || value.Id != excludedAddressId).OrderBy(value => value.Id).ToArrayAsync(),
            OrderItems = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }
}
