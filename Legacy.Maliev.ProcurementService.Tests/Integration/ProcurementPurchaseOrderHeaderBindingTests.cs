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
using Microsoft.Extensions.Options;
using Newtonsoft.Json;

using JsonException = System.Text.Json.JsonException;
using JsonSerializer = System.Text.Json.JsonSerializer;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementPurchaseOrderHeaderBindingTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] TextFields = ["SupplierContactPerson", "ShippingContactPerson", "ShippingTelephone", "ShippingMobile", "ShippingFax", "BillingContactPerson", "BillingTelephone", "BillingMobile", "BillingFax", "Fob", "Terms", "ShippingMethod", "Notes"];
    private static readonly string[] ReferenceFields = ["SupplierId", "ShippingAddressId", "BillingAddressId", "EmployeeId"];
    private ProcurementRuntimeFactory app = null!;
    private JsonSerializerOptions Options => app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;

    public async Task InitializeAsync()
    {
        try
        {
            await fixture.ResetAsync();
            app = fixture.CreateFactory(true);
            await using var scope = app.Services.CreateAsyncScope();
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Addresses.Add(new SupplierAddress { Id = 8000, Address1 = "Synthetic supplier address", CountryId = 7 });
            suppliers.Suppliers.Add(new Supplier { Id = 8000, Name = "Synthetic supplier", AddressId = 8000 });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.Add(new PurchaseOrderAddress { Id = 8000, AddressLine1 = "Synthetic PO address", CountryId = 7 });
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 8000, SupplierId = 8000, ShippingAddressId = 8000, BillingAddressId = 8000, Notes = "Untouched sentinel" });
            orders.Files.Add(new PurchaseOrderFile { Id = 8000, PurchaseOrderId = 8000, Bucket = "synthetic", ObjectName = "metadata-only" });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            // xUnit v2 skips IAsyncLifetime.DisposeAsync when InitializeAsync throws.
            // Close only this class's factory and retain both failures if cleanup also fails.
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Header test initialization and cleanup both failed.", initializationFailure, cleanupFailure);
            }
            throw;
        }
    }

    public Task DisposeAsync()
    {
        var owned = app;
        app = null!;
        return owned is null ? Task.CompletedTask : owned.DisposeAsync().AsTask();
    }

    [Theory]
    [InlineData("null", null)]
    [InlineData("\"\"", "")]
    [InlineData("\" padded \"", " padded ")]
    [InlineData("\"ไทย\"", "ไทย")]
    [InlineData("-42", "-42")]
    [InlineData("12.50", "12.50")]
    [InlineData("1e2", "1e2")]
    [InlineData("true", "true")]
    [InlineData("false", "false")]
    public void AllTextFields_MatchPinnedPublicTypedReader(string token, string? expected)
    {
        // Public Newtonsoft 13.0.3 primitive contract, not the original deployed model/binary.
        using var reader = PublicReader(token);
        Assert.Equal(expected, reader.ReadAsString());
        var value = Bind("{" + string.Join(",", TextFields.Select(field => $"\"{field}\":{token}")) + "}");
        foreach (var field in TextFields) Assert.Equal(expected, Property(value, field));
    }

    [Theory]
    [InlineData("null", null)]
    [InlineData("\"\"", null)]
    [InlineData("1", 1)]
    [InlineData("-1", -1)]
    [InlineData("\"42\"", 42)]
    [InlineData("\" 42 \"", 42)]
    [InlineData("\"+42\"", 42)]
    [InlineData("\"-2147483648\"", int.MinValue)]
    public void AllReferenceFields_MatchPinnedPublicTypedReader(string token, int? expected)
    {
        using var reader = PublicReader(token);
        Assert.Equal(expected, reader.ReadAsInt32());
        var value = Bind("{" + string.Join(",", ReferenceFields.Select(field => $"\"{field}\":{token}")) + "}");
        foreach (var field in ReferenceFields) Assert.Equal((object?)expected, Property(value, field));
    }

    public static IEnumerable<object[]> InvalidShapes()
        => TextFields.Concat(ReferenceFields).SelectMany(field => new[] { "{}", "[]" }.Select(token => new object[] { field, token }));

    [Theory]
    [MemberData(nameof(InvalidShapes))]
    public void EveryRecognizedField_RejectsObjectsAndArrays(string field, string token)
    {
        using var reader = PublicReader(token);
        Assert.Throws<JsonReaderException>(() => ReadPublic(reader, field));
        Assert.Throws<JsonException>(() => Bind($"{{\"{field}\":{token}}}"));
    }

    public static IEnumerable<object[]> InvalidReferences()
        => ReferenceFields.SelectMany(field => new[] { "true", "1.5", "2147483648" }.Select(token => new object[] { field, token }));

    [Theory]
    [MemberData(nameof(InvalidReferences))]
    public void EveryReference_RejectsBooleanFractionAndOverflow(string field, string token)
    {
        using var reader = PublicReader(token);
        Assert.Throws<JsonReaderException>(() => reader.ReadAsInt32());
        Assert.Throws<JsonException>(() => Bind($"{{\"{field}\":{token}}}"));
    }

    [Theory]
    [InlineData("null")]
    [InlineData("\"\"")]
    [InlineData("replacement")]
    public void AllFields_DuplicateAssignmentsAreOrderedAndTypedNullsAreSkipped(string mode)
    {
        foreach (var field in TextFields.Concat(ReferenceFields))
        {
            var text = TextFields.Contains(field);
            var later = mode == "replacement" ? (text ? "\"last\"" : "8") : mode;
            var value = Bind($"{{\"{field}\":{(text ? "\"first\"" : "7")},\"{field.ToLowerInvariant()}\":{later}}}");
            object expected = mode == "replacement" ? (text ? (object)"last" : 8)
                : text ? (mode == "\"\"" ? "" : "first") : 7;
            Assert.Equal(expected, Property(value, field));
        }
    }

    public static IEnumerable<object[]> InvalidDuplicates()
        => TextFields.Concat(ReferenceFields).SelectMany(field => new[] { false, true }.Select(badFirst => new object[] { field, badFirst }));

    [Theory]
    [MemberData(nameof(InvalidDuplicates))]
    public void EveryMalformedOccurrence_RejectsEvenWhenAnotherDuplicateIsValid(string field, bool badFirst)
    {
        var valid = TextFields.Contains(field) ? "\"valid\"" : "7";
        var payload = $"{{\"{field}\":{(badFirst ? "{}" : valid)},\"{field}\":{(badFirst ? valid : "{}")}}}";
        Assert.Throws<JsonException>(() => Bind(payload));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void FreshOmittedOrExplicitNullFields_DefaultToNull(bool explicitNull)
    {
        var value = Bind(explicitNull ? "{" + string.Join(",", TextFields.Concat(ReferenceFields).Select(field => $"\"{field}\":null")) + "}" : "{}");
        foreach (var field in TextFields.Concat(ReferenceFields)) Assert.Null(Property(value, field));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HttpNumericText_PreservesDistinctContactsAndAllHeaderFields(bool update)
    {
        var tokens = TextFields.Select((field, index) => (Field: field, Token: (index + 10).ToString(CultureInfo.InvariantCulture))).ToDictionary(value => value.Field, value => value.Token);
        await AssertSuccessAsync(update, Payload(tokens), tokens.ToDictionary(value => value.Key, value => (string?)value.Value), true);
    }

    [Theory]
    [InlineData(false, "true")]
    [InlineData(true, "true")]
    [InlineData(false, "false")]
    [InlineData(true, "false")]
    public Task HttpBooleanText_PersistsLowercaseStrings(bool update, string token)
        => AssertSuccessAsync(update, Payload(TextFields.ToDictionary(field => field, _ => token)), TextFields.ToDictionary(field => field, _ => (string?)token), true);

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public Task HttpOmissionAndNull_ClearNullableHeaderProjection(bool update, bool omitted)
        => AssertSuccessAsync(update, omitted ? "{}" : "{" + string.Join(",", TextFields.Concat(ReferenceFields).Select(field => $"\"{field}\":null")) + "}",
            TextFields.ToDictionary(field => field, _ => (string?)null), false);

    [Theory]
    [InlineData(false, "Notes", "{\"Marker\":\"SYNTHETIC-PRIVATE-HEADER\"}")]
    [InlineData(true, "Notes", "{\"Marker\":\"SYNTHETIC-PRIVATE-HEADER\"}")]
    [InlineData(false, "SupplierId", "\"SYNTHETIC-PRIVATE-HEADER\"")]
    [InlineData(true, "SupplierId", "\"SYNTHETIC-PRIVATE-HEADER\"")]
    public Task HttpMalformedRecognizedField_RefusesBeforeWrites(bool update, string field, string token)
        => AssertRefusedAsync(update, $"{{\"{field}\":{token}}}", HttpStatusCode.BadRequest);

    [Theory]
    [InlineData(false, "Notes")]
    [InlineData(true, "Notes")]
    [InlineData(false, "SupplierId")]
    [InlineData(true, "SupplierId")]
    public async Task HttpDuplicateNull_DoesNotEraseEarlierAssignment(bool update, string field)
    {
        var text = field == "Notes";
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync(original?.Id);
        using var response = await SendAsync(client, update, original?.Id ?? 0, $"{{\"{field}\":{(text ? "\"retained\"" : "8000")},\"{field.ToLowerInvariant()}\":null}}");
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!.Id;
        var current = (await client.GetFromJsonAsync<PurchaseOrderResponse>($"/PurchaseOrders/{id}"))!;
        Assert.Equal(text ? (object)"retained" : 8000, typeof(PurchaseOrderResponse).GetProperty(field)!.GetValue(current));
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    [Theory]
    [InlineData(false, "Notes")]
    [InlineData(true, "Notes")]
    [InlineData(false, "SupplierId")]
    [InlineData(true, "SupplierId")]
    public Task HttpBadFirstDuplicate_CannotBeHidden(bool update, string field)
        => AssertRefusedAsync(update, $"{{\"{field}\":{{}},\"{field}\":{(field == "Notes" ? "\"valid\"" : "8000")}}}", HttpStatusCode.BadRequest);

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task HttpAnonymousOrWrongPermission_CannotWrite(bool update, bool anonymous)
    {
        using var writer = Writer();
        var original = update ? await PrepareAsync(writer) : null;
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, original?.Id ?? 0, "{\"Notes\":123}");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [InlineData(false, "null")]
    [InlineData(true, "null")]
    [InlineData(false, "[]")]
    [InlineData(true, "[]")]
    public Task HttpWrongRoot_IsBadRequestWithoutWrites(bool update, string payload)
        => AssertRefusedAsync(update, payload, HttpStatusCode.BadRequest);

    [Theory]
    [InlineData("shippingcontactperson", true)]
    [InlineData("\u017FhippingContactPerson", false)]
    public void PropertyLookup_MatchesPinnedPublicOrdinalComparer(string inputName, bool recognized)
    {
        var properties = new Newtonsoft.Json.Serialization.JsonPropertyCollection(typeof(UpsertPurchaseOrderRequest));
        properties.AddProperty(new Newtonsoft.Json.Serialization.JsonProperty { PropertyName = "ShippingContactPerson" });
        Assert.Equal(recognized, properties.GetClosestMatchProperty(inputName) is not null);
        var token = recognized ? "123" : "{}";
        var value = Bind($"{{\"{inputName}\":{token}}}");
        Assert.Equal(recognized ? "123" : null, value.ShippingContactPerson);
    }

    [Fact]
    public void Converter_IsMvcRequestOnly_PreservesWriteShapeAndSkipsUnknownGraphs()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Notes\":123}"));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<PurchaseOrderResponse>("{\"Notes\":123}", Options));
        var value = Bind("{\"Notes\":12.50,\"EmployeeId\":\"42\",\"Unknown\":{\"Notes\":{}},\"OrderItem\":[{\"Notes\":[]}],\"Id\":null,\"CreatedDate\":null}");
        Assert.Equal("12.50", value.Notes);
        Assert.Equal(42, value.EmployeeId);
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(value, Options));
        Assert.Equal(new[] { "EmployeeId", "Notes" }, wire.RootElement.EnumerateObject().Select(property => property.Name).OrderBy(name => name).ToArray());
        Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty("Notes").ValueKind);
        Assert.Equal(JsonValueKind.Number, wire.RootElement.GetProperty("EmployeeId").ValueKind);
        Assert.Throws<JsonException>(() => Bind("{\"Notes\":\"valid\"} {}"));
        foreach (var root in new[] { "42", "true", "\"text\"", "{\"Notes\":01}" })
            Assert.Throws<JsonException>(() => Bind(root));
        foreach (var token in new[] { "-0", "1E+03", "9223372036854775808", "1e400" })
        {
            using var reader = PublicReader(token);
            Assert.Equal(reader.ReadAsString(), Bind($"{{\"Notes\":{token}}}").Notes);
        }
    }

    private UpsertPurchaseOrderRequest Bind(string payload) => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>(payload, Options)!;
    private static object? Property(UpsertPurchaseOrderRequest value, string field) => typeof(UpsertPurchaseOrderRequest).GetProperty(field)!.GetValue(value);
    private static JsonTextReader PublicReader(string token) => new(new StringReader(token)) { Culture = CultureInfo.InvariantCulture, CloseInput = true };
    private static object? ReadPublic(JsonTextReader reader, string field) => TextFields.Contains(field) ? reader.ReadAsString() : (object?)reader.ReadAsInt32();
    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.PurchaseOrdersUpdate, ProcurementPermissions.PurchaseOrdersRead);
    private static string Payload(Dictionary<string, string> text) => "{" + string.Join(",", text.Select(value => $"\"{value.Key}\":{value.Value}")) + ",\"SupplierId\":8000,\"ShippingAddressId\":8000,\"BillingAddressId\":8000,\"EmployeeId\":123}";

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, int id, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return update ? await client.PutAsync($"/PurchaseOrders/{id}", content) : await client.PostAsync("/PurchaseOrders", content);
    }

    private static async Task<PurchaseOrderResponse> PrepareAsync(HttpClient client)
    {
        using var response = await client.PostAsJsonAsync("/PurchaseOrders", new UpsertPurchaseOrderRequest(8000, "Supplier control", 8000, "Shipping control", "Old", "Old", "Old", 8000, "Old", "Old", "Old", "Old", "Old", "Old", "Old", 123, "Old"));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
    }

    private async Task AssertSuccessAsync(bool update, string payload, Dictionary<string, string?> expected, bool withReferences)
    {
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync(original?.Id);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, original?.Id ?? 0, payload);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = original?.Id ?? (await response.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!.Id;
        if (!update)
        {
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!.Id);
        }
        var current = (await client.GetFromJsonAsync<PurchaseOrderResponse>($"/PurchaseOrders/{id}"))!;
        using var fresh = await client.GetAsync($"/PurchaseOrders/{id}");
        using var wire = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        if (!update) expected = new Dictionary<string, string?>(expected) { ["SupplierContactPerson"] = expected["ShippingContactPerson"] };
        foreach (var field in TextFields)
        {
            Assert.Equal(expected[field], typeof(PurchaseOrderResponse).GetProperty(field)!.GetValue(current));
            if (expected[field] is null) Assert.False(wire.RootElement.TryGetProperty(field, out _));
            else
            {
                Assert.Equal(JsonValueKind.String, wire.RootElement.GetProperty(field).ValueKind);
                Assert.Equal(expected[field], wire.RootElement.GetProperty(field).GetString());
            }
        }
        Assert.Equal(withReferences ? (int?)8000 : null, current.SupplierId);
        Assert.Equal(withReferences ? (int?)8000 : null, current.ShippingAddressId);
        Assert.Equal(withReferences ? (int?)8000 : null, current.BillingAddressId);
        Assert.Equal(withReferences ? (int?)123 : null, current.EmployeeId);
        foreach (var field in ReferenceFields)
        {
            if (withReferences) Assert.Equal(JsonValueKind.Number, wire.RootElement.GetProperty(field).ValueKind);
            else Assert.False(wire.RootElement.TryGetProperty(field, out _));
        }
        Assert.NotNull(current.CreatedDate);
        Assert.Equal(DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified), current.ModifiedDate);
        if (original is not null)
        {
            Assert.Equal(original.CreatedDate, current.CreatedDate);
            Assert.True(current.ModifiedDate > original.ModifiedDate);
        }
        else Assert.Equal(current.CreatedDate, current.ModifiedDate);
        Assert.NotEqual(8000, id);
        await VerifyRowAsync(current);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    private async Task AssertRefusedAsync(bool update, string payload, HttpStatusCode status)
    {
        using var client = Writer();
        var original = update ? await PrepareAsync(client) : null;
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, original?.Id ?? 0, payload);
        Assert.Equal(status, response.StatusCode);
        Assert.DoesNotContain("SYNTHETIC-PRIVATE-HEADER", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
    }

    private async Task VerifyRowAsync(PurchaseOrderResponse current)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var row = await db.PurchaseOrders.AsNoTracking().SingleAsync(value => value.Id == current.Id);
        foreach (var field in TextFields.Concat(ReferenceFields))
            Assert.Equal(typeof(PurchaseOrderResponse).GetProperty(field)!.GetValue(current), typeof(PurchaseOrder).GetProperty(field)!.GetValue(row));
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(2, await db.PurchaseOrders.CountAsync());
    }

    private async Task<string> SnapshotAsync(int? excludedOrder = null)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().OrderBy(value => value.Id).Select(value => new { value.Id, value.Name, value.AddressId }).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).Select(value => new { value.Id, value.Address1, value.CountryId }).ToArrayAsync(),
            Orders = await orders.PurchaseOrders.AsNoTracking().Where(value => excludedOrder == null || value.Id != excludedOrder).OrderBy(value => value.Id).Select(value => new
            {
                value.Id,
                value.SupplierId,
                value.SupplierContactPerson,
                value.ShippingAddressId,
                value.ShippingContactPerson,
                value.ShippingTelephone,
                value.ShippingMobile,
                value.ShippingFax,
                value.BillingAddressId,
                value.BillingContactPerson,
                value.BillingTelephone,
                value.BillingMobile,
                value.BillingFax,
                value.Fob,
                value.Terms,
                value.ShippingMethod,
                value.EmployeeId,
                value.Notes,
                value.CreatedDate,
                value.ModifiedDate,
            }).ToArrayAsync(),
            Addresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).Select(value => new { value.Id, value.AddressLine1, value.CountryId }).ToArrayAsync(),
            Items = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).Select(value => new { value.Id, value.PurchaseOrderId, value.PartNumber }).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).Select(value => new { value.Id, value.PurchaseOrderId, value.Bucket, value.ObjectName }).ToArrayAsync(),
        });
    }
}
