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

public sealed class ProcurementSupplierAddressScalarStringTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] Fields = ["Building", "Address1", "Address2", "City", "State", "PostalCode"];

    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Addresses.Add(new SupplierAddress { Id = 80, Address1 = "Unrelated address", CountryId = 7 });
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
    public async Task PostAndPut_SourcePrimitiveAddressFields_PreserveStringsAndAttachment(bool update, string token, string expected)
    {
        using var client = Writer();
        var (supplier, original) = await PrepareAsync(client, update);
        var before = await SnapshotAsync(update ? null : supplier.Id, original?.Id);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, update ? original!.Id : supplier.Id, Payload(token));
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<SupplierAddressResponse>())!.Id;
        if (!update)
        {
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<SupplierAddressResponse>())!.Id);
        }
        using var fresh = await client.GetAsync($"/suppliers/addresses/{id}");
        Assert.Equal(HttpStatusCode.OK, fresh.StatusCode);
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        foreach (var field in Fields)
        {
            Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty(field).ValueKind);
            Assert.Equal(expected, wire.RootElement.GetProperty(field).GetString());
        }
        Assert.Equal(JsonValueKind.Number, wire.RootElement.GetProperty("CountryId").ValueKind);
        Assert.Equal(7, wire.RootElement.GetProperty("CountryId").GetInt32());
        Assert.False(wire.RootElement.TryGetProperty("AddressLine1", out _));
        var current = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{id}"))!;
        Assert.Equal(Enumerable.Repeat(expected, Fields.Length), Text(current));
        Assert.Equal(current, await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/{supplier.Id}/addresses"));
        var owner = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{supplier.Id}"))!;
        if (update)
        {
            Assert.Equal(supplier, owner);
            Assert.Equal(original!.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
        }
        else
        {
            Assert.Equal(supplier with { AddressId = id, ModifiedDate = owner.ModifiedDate }, owner);
            Assert.True(owner.ModifiedDate > supplier.ModifiedDate);
            Assert.NotNull(current.CreatedDate);
            Assert.Equal(current.CreatedDate, current.ModifiedDate);
        }
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(update ? null : supplier.Id, id));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task OptionalAddressFields_NullOrOmitted_RemainNullable(bool update, bool omitted)
    {
        using var client = Writer();
        var (supplier, original) = await PrepareAsync(client, update);
        var before = await SnapshotAsync(update ? null : supplier.Id, original?.Id);
        var body = "{\"Address1\":\"Required line\",\"CountryId\":7" + (omitted ? "}" : "," + string.Join(",", Fields.Where(field => field != "Address1").Select(field => $"\"{field}\":null")) + "}");
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, update ? original!.Id : supplier.Id, body);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<SupplierAddressResponse>())!.Id;
        var current = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{id}"))!;
        Assert.Equal(new string?[] { null, "Required line", null, null, null, null }, Text(current));
        using var fresh = await client.GetAsync($"/suppliers/addresses/{id}");
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        foreach (var field in Fields.Where(field => field != "Address1")) Assert.False(wire.RootElement.TryGetProperty(field, out _));
        if (original is not null)
        {
            Assert.Equal(original.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
        }
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(update ? null : supplier.Id, id));
    }

    [Theory]
    [InlineData("Building")]
    [InlineData("Address1")]
    [InlineData("Address2")]
    [InlineData("City")]
    [InlineData("State")]
    [InlineData("PostalCode")]
    public async Task EveryTextProperty_RejectsNestedObjectAndArray_OnBothRoutes(string field)
    {
        using var client = Writer();
        var (supplier, original) = await PrepareAsync(client, true);
        var before = await SnapshotAsync();
        foreach (var update in new[] { false, true })
        foreach (var nested in new[] { "[]", "{}" })
        {
            var body = "{" + string.Join(",", Fields.Select(value => $"\"{value}\":{(value == field ? nested : "\"Valid\"")}")) + ",\"CountryId\":7}";
            using var response = await SendAsync(client, update, update ? original!.Id : supplier.Id, body);
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(before, await SnapshotAsync());
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ScalarAddressWrite_AnonymousOrReadGrant_CannotMutateGraph(bool update, bool anonymous)
    {
        using var owner = Writer();
        var (supplier, original) = await PrepareAsync(owner, update);
        using var client = anonymous ? fixture.Factory.CreateClient() : fixture.Client(ProcurementPermissions.SupplierAddressesRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, update ? original!.Id : supplier.Id, Payload("123"));
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingOwnerOrAddress_WithSourceScalarText_ReachesNotFoundWithoutWrites(bool update)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, 999999, Payload("true"));
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public async Task CurrentCreateNullRequiredLineGuard_IsUnchanged()
    {
        using var client = Writer();
        var (supplier, _) = await PrepareAsync(client, false);
        var before = await SnapshotAsync();
        using var nullLine = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", new UpsertSupplierAddressRequest(null, null, null, null, null, null, 7));
        Assert.Equal(HttpStatusCode.BadRequest, nullLine.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public async Task ExistingLiteralUpdate_EmptyTextAndZeroCountry_RemainUnchanged()
    {
        using var client = Writer();
        var (supplier, original) = await PrepareAsync(client, true);
        var before = await SnapshotAsync(null, original!.Id);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await client.PutAsJsonAsync($"/suppliers/addresses/{original.Id}", new UpsertSupplierAddressRequest("", "", "", "", "", "", 0));
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        var current = (await client.GetFromJsonAsync<SupplierAddressResponse>($"/suppliers/addresses/{original.Id}"))!;
        Assert.Equal(Enumerable.Repeat("", Fields.Length), Text(current));
        Assert.Equal(0, current.CountryId);
        Assert.Equal(original.CreatedDate, current.CreatedDate);
        Assert.True(current.ModifiedDate > original.ModifiedDate);
        Assert.Equal(supplier, await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{supplier.Id}"));
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(null, original.Id));
    }

    [Fact]
    public void Converter_IsAddressRequestLocal_AndWritesStringsWithoutChangingCountry()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Notes\":123}"));
        var request = JsonSerializer.Deserialize<UpsertSupplierAddressRequest>(Payload("1.2300E+03"))!;
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(request));
        foreach (var field in Fields)
        {
            Assert.Equal(JsonValueKind.String, document.RootElement.GetProperty(field).ValueKind);
            Assert.Equal("1.2300E+03", document.RootElement.GetProperty(field).GetString());
        }
        Assert.Equal(7, document.RootElement.GetProperty("CountryId").GetInt32());
    }

    private HttpClient Writer() => fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersRead,
        ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead);

    private static string Payload(string token) => "{" + string.Join(",", Fields.Select(field => $"\"{field}\":{token}")) + ",\"CountryId\":7}";
    private static string?[] Text(SupplierAddressResponse value) => [value.Building, value.Address1, value.Address2, value.City, value.State, value.PostalCode];

    private async Task<(SupplierResponse Supplier, SupplierAddressResponse? Address)> PrepareAsync(HttpClient client, bool address)
    {
        using var created = await client.PostAsJsonAsync("/Suppliers", new { Name = "Address owner" });
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var supplier = (await created.Content.ReadFromJsonAsync<SupplierResponse>())!;
        if (!address) return (supplier, null);
        using var attached = await client.PostAsJsonAsync($"/suppliers/{supplier.Id}/addresses", new UpsertSupplierAddressRequest("Original", "Original", "Original", "Original", "Original", "Original", 7));
        Assert.Equal(HttpStatusCode.Created, attached.StatusCode);
        var row = (await attached.Content.ReadFromJsonAsync<SupplierAddressResponse>())!;
        return ((await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{supplier.Id}"))!, row);
    }

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return update ? await client.PutAsync($"/suppliers/addresses/{id}", content) : await client.PostAsync($"/suppliers/{id}/addresses", content);
    }

    private async Task VerifyRowAsync(SupplierAddressResponse current)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await suppliers.Addresses.AsNoTracking().SingleAsync(value => value.Id == current.Id);
        Assert.Equal(Text(current), new string?[] { row.Building, row.Address1, row.Address2, row.City, row.State, row.PostalCode });
        Assert.Equal(current.CountryId, row.CountryId);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(2, await suppliers.Addresses.CountAsync());
        Assert.Equal(2, await suppliers.Suppliers.CountAsync());
    }

    private async Task<string> SnapshotAsync(int? excludedSupplierId = null, int? excludedAddressId = null)
    {
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().Where(value => excludedSupplierId == null || value.Id != excludedSupplierId).OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().Where(value => excludedAddressId == null || value.Id != excludedAddressId).OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrderAddresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            OrderItems = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }
}
