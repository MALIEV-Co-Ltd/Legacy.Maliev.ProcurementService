using System.Buffers;
using System.Globalization;
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

public sealed class ProcurementSupplierScalarStringTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] Fields = ["Name", "Website", "TaxNumber", "Email", "Note", "Telephone", "Mobile", "Fax"];

    public async Task InitializeAsync()
    {
        await fixture.ResetAsync();
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        suppliers.Addresses.Add(new SupplierAddress { Id = 7001, Address1 = "Supplier sentinel", CountryId = 1 });
        suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "Unrelated supplier", AddressId = 7001 });
        await suppliers.SaveChangesAsync();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        orders.Addresses.Add(new PurchaseOrderAddress { Id = 7003, AddressLine1 = "PO sentinel", CountryId = 1 });
        orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003, Notes = "Unrelated order" });
        orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "Sentinel" });
        orders.Files.Add(new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "sentinel", ObjectName = "metadata-only" });
        await orders.SaveChangesAsync();
    }

    public Task DisposeAsync() => Task.CompletedTask;

    [Theory]
    [InlineData(false, "123", "123")]
    [InlineData(true, "123", "123")]
    [InlineData(false, "-0", "-0")]
    [InlineData(true, "-0", "-0")]
    [InlineData(false, "12.3400", "12.3400")]
    [InlineData(true, "12.3400", "12.3400")]
    [InlineData(false, "1E+03", "1E+03")]
    [InlineData(true, "1E+03", "1E+03")]
    [InlineData(false, "0.001e-2", "0.001e-2")]
    [InlineData(true, "0.001e-2", "0.001e-2")]
    [InlineData(false, "9223372036854775808", "9223372036854775808")]
    [InlineData(true, "9223372036854775808", "9223372036854775808")]
    [InlineData(false, "true", "true")]
    [InlineData(true, "true", "true")]
    [InlineData(false, "false", "false")]
    [InlineData(true, "false", "false")]
    [InlineData(false, "\"  ไทย +00123  \"", "  ไทย +00123  ")]
    [InlineData(true, "\"  ไทย +00123  \"", "  ไทย +00123  ")]
    [InlineData(false, "\"\"", "")]
    [InlineData(true, "\"\"", "")]
    [InlineData(false, "\"   \"", "   ")]
    [InlineData(true, "\"   \"", "   ")]
    public async Task SupplierPostAndPut_SourceScalarText_PreservesLexemeAndStringResponse(bool update, string token, string expected)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var preservedGraph = await SnapshotAsync(update ? id : null);
        SupplierResponse? original = update ? await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}") : null;
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, id, Payload(token));
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
        using var fresh = await client.GetAsync($"/Suppliers/{id}");
        Assert.Equal(HttpStatusCode.OK, fresh.StatusCode);
        using var document = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        foreach (var field in Fields)
        {
            var value = document.RootElement.GetProperty(field);
            Assert.Equal(JsonValueKind.String, value.ValueKind);
            Assert.Equal(expected, value.GetString());
        }
        var current = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
        if (update)
        {
            Assert.Equal(original!.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
            Assert.Equal(original.AddressId, current.AddressId);
        }
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var row = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.Equal(Enumerable.Repeat(expected, Fields.Length), new[] { row.Name, row.Website, row.TaxNumber, row.Email, row.Note, row.Telephone, row.Mobile, row.Fax });
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(update ? 7001 : null, row.AddressId);
        Assert.Equal(2, await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
        Assert.Equal(preservedGraph, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task OptionalSupplierText_NullAndOmission_RemainNullAndOmittedOnWire(bool update, bool omit)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var preservedGraph = await SnapshotAsync(update ? id : null);
        var payload = omit ? "{\"Name\":\"ชื่อไทย\"}" : "{\"Name\":\"ชื่อไทย\"," + string.Join(",", Fields.Skip(1).Select(field => $"\"{field}\":null")) + "}";
        using var response = await SendAsync(client, update, id, payload);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update) id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        using var fresh = await client.GetAsync($"/Suppliers/{id}");
        using var document = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        Assert.Equal("ชื่อไทย", document.RootElement.GetProperty("Name").GetString());
        foreach (var field in Fields.Skip(1)) Assert.False(document.RootElement.TryGetProperty(field, out _));
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var row = await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.All(new[] { row.Website, row.TaxNumber, row.Email, row.Note, row.Telephone, row.Mobile, row.Fax }, Assert.Null);
        Assert.Equal(update ? 7001 : null, row.AddressId);
        Assert.Equal(2, await scope.ServiceProvider.GetRequiredService<SupplierDbContext>().Suppliers.CountAsync());
        Assert.Equal(preservedGraph, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task NullAndOmittedSupplierName_KeepRequiredStorageRefusalAndGraphUnchanged(bool update, bool omit)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var payload = "{" + (omit ? "" : "\"Name\":null,")
            + string.Join(",", Fields.Skip(1).Select(field => $"\"{field}\":\"Refused write\"")) + "}";
        Assert.Null(JsonSerializer.Deserialize<UpsertSupplierRequest>(payload)!.Name);
        await using (var scope = fixture.Factory.Services.CreateAsyncScope())
        {
            var context = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            Assert.False(context.Model.FindEntityType(typeof(Supplier))!.FindProperty(nameof(Supplier.Name))!.IsNullable);
        }
        var before = await SnapshotAsync();
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, id, payload);
        // The normal Program middleware renders the required-storage failure in TestServer.
        // This is not evidence of the original deployed binary or a Kestrel wire execution.
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        if (update)
        {
            var current = (await client.GetFromJsonAsync<SupplierResponse>($"/Suppliers/{id}"))!;
            Assert.Equal("Control", current.Name);
            Assert.Equal(7001, current.AddressId);
        }
    }

    [Theory]
    [InlineData(false, "[]")]
    [InlineData(true, "[]")]
    [InlineData(false, "{}")]
    [InlineData(true, "{}")]
    [InlineData(false, "01")]
    [InlineData(true, "01")]
    [InlineData(false, "tru")]
    [InlineData(true, "tru")]
    public async Task InvalidSupplierScalarShapeOrJson_IsBadRequestWithoutAnyGraphChange(bool update, string token)
    {
        using var client = Writer();
        var id = update ? await CreateControlAsync(client) : 0;
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, id, Payload(token));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ScalarSupplierRequest_AnonymousOrWrongGrant_StillCannotWrite(bool update, bool anonymous)
    {
        using var owner = Writer();
        var id = update ? await CreateControlAsync(owner) : 0;
        using var client = anonymous ? fixture.Factory.CreateClient() : fixture.Client(ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, id, Payload("123"));
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public void CompatibilityIsSupplierRequestOnly_AndWritesTextTokens()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Notes\":123}"));
        var request = JsonSerializer.Deserialize<UpsertSupplierRequest>(Payload("123"))!;
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(request));
        foreach (var field in Fields)
        {
            Assert.Equal(JsonValueKind.String, document.RootElement.GetProperty(field).ValueKind);
            Assert.Equal("123", document.RootElement.GetProperty(field).GetString());
        }
    }

    [Theory]
    [InlineData("fr-FR")]
    [InlineData("th-TH")]
    [InlineData("tr-TR")]
    public void NumericText_UsesInvariantValidationAndRetainsLexeme(string culture)
    {
        var previous = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(culture);
            var request = JsonSerializer.Deserialize<UpsertSupplierRequest>(Payload("12.3400E+03"))!;
            Assert.Equal(Enumerable.Repeat("12.3400E+03", Fields.Length), new[] { request.Name, request.Website, request.TaxNumber, request.Email, request.Note, request.Telephone, request.Mobile, request.Fax });
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void NumericText_ContiguousAndSegmentedReaderRetainIdenticalLexeme(bool segmented)
    {
        var bytes = Encoding.UTF8.GetBytes("12.3400E+03");
        var first = new ByteSegment(bytes.AsMemory(0, 3));
        var last = first.Append(bytes.AsMemory(3));
        var sequence = new ReadOnlySequence<byte>(first, 0, last, last.Memory.Length);
        var reader = segmented ? new Utf8JsonReader(sequence, true, default) : new Utf8JsonReader(bytes);
        Assert.True(reader.Read());
        Assert.Equal(segmented, reader.HasValueSequence);
        Assert.Equal("12.3400E+03", new SupplierScalarStringJsonConverter().Read(ref reader, typeof(string), new JsonSerializerOptions()));
        Assert.False(reader.Read());
    }

    private HttpClient Writer() => fixture.Client(ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead);

    private static string Payload(string token) => "{" + string.Join(",", Fields.Select(field => $"\"{field}\":{token}")) + "}";

    private async Task<int> CreateControlAsync(HttpClient client)
    {
        using var response = await client.PostAsJsonAsync("/Suppliers", new UpsertSupplierRequest("Control", "Old website", "Old tax", "Old email", "Old note", "Old telephone", "Old mobile", "Old fax"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var id = (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        await using var scope = fixture.Factory.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await suppliers.Suppliers.SingleAsync(value => value.Id == id);
        row.AddressId = 7001;
        await suppliers.SaveChangesAsync();
        return id;
    }

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
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

    private sealed class ByteSegment : ReadOnlySequenceSegment<byte>
    {
        public ByteSegment(ReadOnlyMemory<byte> memory) => Memory = memory;

        public ByteSegment Append(ReadOnlyMemory<byte> memory)
        {
            var next = new ByteSegment(memory) { RunningIndex = RunningIndex + Memory.Length };
            Next = next;
            return next;
        }
    }
}
