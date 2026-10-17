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

public sealed class ProcurementHeaderIgnoredFieldsTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] Fields = ["Id", "CreatedDate", "ModifiedDate"];
    private static readonly string[] ValidIds = ["0", "-17", "2147483647", "-2147483648", "\"42\"", "\" +42 \"", "\"\"", "null", "123", "7007"];
    private static readonly string[] InvalidIds = ["1.5", "1e3", "true", "false", "[]", "{}", "2147483648", "-2147483649", "\"SYNTHETIC-PRIVATE-HEADER-ID\"", "\"1.0\"", "\"2147483648\"", "\"null\""];
    private static readonly string[] ValidDates = ["null", "\"\"", "\"2000-02-29\"", "\"2000-02-29T12:34:56Z\"", "\"2000-02-29T12:34:56+07:00\"", "\"/Date(0)/\"", "\"2000-02-29T24:00:00Z\"", "\"02/03/2000\"", "\"2000-02-29T12:34:56.1234567Z\"", "\"/Date(0+0700)/\""];
    private static readonly string[] InvalidDates = ["0", "-1", "1.5", "true", "false", "[]", "{}", "\"SYNTHETIC-PRIVATE-HEADER-DATE\"", "\"2000-02-30\"", "\"2000-13-01\"", "\"2000-02-29T24:00:01Z\"", "\"9999-12-31T24:00:00Z\""];
    private ProcurementRuntimeFactory app = null!;
    private JsonSerializerOptions Options => app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;
    private DateTime Now() => DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);

    public async Task InitializeAsync()
    {
        try
        {
            await fixture.ResetAsync();
            app = fixture.CreateFactory(true);
            await using var scope = app.Services.CreateAsyncScope();
            var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
            suppliers.Addresses.Add(new SupplierAddress { Id = 7001, Address1 = "sentinel", CountryId = 7 });
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "sentinel", AddressId = 7001 });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.Add(new PurchaseOrderAddress { Id = 7003, AddressLine1 = "sentinel", CountryId = 7 });
            orders.PurchaseOrders.AddRange(
                new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003, Notes = "original", CreatedDate = Now().AddDays(-2), ModifiedDate = Now().AddDays(-1) },
                new PurchaseOrder { Id = 7007, Notes = "untouched body identity", CreatedDate = Now().AddDays(-3), ModifiedDate = Now().AddDays(-3) });
            orders.Files.Add(new PurchaseOrderFile { Id = 7005, PurchaseOrderId = 7004, Bucket = "sentinel", ObjectName = "metadata-only" });
            orders.OrderItems.Add(new OrderItem { Id = 7006, PurchaseOrderId = 7004, PartNumber = "sentinel" });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Ignored header fields initialization and cleanup both failed.", initializationFailure, cleanupFailure);
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

    private static IEnumerable<object[]> Cross(bool valid)
        => Fields.SelectMany(field => (field == "Id" ? (valid ? ValidIds : InvalidIds) : (valid ? ValidDates : InvalidDates))
            .SelectMany(token => new[] { new object[] { false, field, token }, new object[] { true, field, token } }));
    public static IEnumerable<object[]> ValidFields => Cross(true);
    public static IEnumerable<object[]> InvalidFields => Cross(false);
    public static IEnumerable<object[]> DuplicateFields => Fields.SelectMany(propertyName => new[] { false, true }.SelectMany(update => new[]
    {
        new object[] { update, propertyName, "bad_first" },
        new object[] { update, propertyName, "bad_last" },
        new object[] { update, propertyName, "bad_scalar_first" },
        new object[] { update, propertyName, "bad_scalar_last" },
        new object[] { update, propertyName, "null_last" },
        new object[] { update, propertyName, "null_first" },
    }));
    public static IEnumerable<object[]> DeniedFields => Fields.SelectMany(propertyName => new[] { false, true }.SelectMany(update => new[]
    {
        new object[] { update, propertyName, false }, new object[] { update, propertyName, true },
    }));
    public static IEnumerable<object[]> MissingFields => Fields.Select(propertyName => new object[] { propertyName });
    public static IEnumerable<object[]> MalformedFields => Fields.SelectMany(propertyName => new[] { new object[] { propertyName, false }, new object[] { propertyName, true } });

    [Theory]
    [MemberData(nameof(ValidFields))]
    public Task ParsedBodyValues_AreDiscardedBeforeServerIdentityAndAuditAssignment(bool update, string field, string token)
        => AssertAppliedAsync(update, "\"" + field.ToLowerInvariant() + "\":" + token + ",");

    [Theory]
    [MemberData(nameof(InvalidFields))]
    public Task InvalidBodyValue_RefusesBeforeAnyWrite(bool update, string field, string token)
        => AssertRefusedAsync(update, "\"" + field + "\":" + token + ",", HttpStatusCode.BadRequest);

    [Theory]
    [MemberData(nameof(DuplicateFields))]
    public Task EveryIgnoredOccurrence_IsValidatedInOrder(bool update, string field, string mode)
    {
        var valid = field == "Id" ? "7007" : "\"2000-02-29T12:34:56Z\"";
        var badScalar = field == "Id" ? "\"SYNTHETIC-PRIVATE-HEADER-ID\"" : "\"2000-02-30\"";
        var first = mode switch { "bad_first" => "{}", "bad_scalar_first" => badScalar, "null_first" => "null", _ => valid };
        var last = mode switch { "bad_last" => "[]", "bad_scalar_last" => badScalar, "null_last" => "null", _ => valid };
        var members = "\"" + field + "\":" + first + ",\"" + field.ToLowerInvariant() + "\":" + last + ",";
        return mode.StartsWith("bad", StringComparison.Ordinal)
            ? AssertRefusedAsync(update, members, HttpStatusCode.BadRequest)
            : AssertAppliedAsync(update, members);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public Task OmittedFieldsAndUnknownNestedGraphs_PreserveCurrentContract(bool update)
        => AssertAppliedAsync(update, "\"Unknown\":{\"Id\":{},\"CreatedDate\":[],\"ModifiedDate\":true},");

    [Theory]
    [MemberData(nameof(DeniedFields))]
    public async Task AuthenticationAndAuthorization_PrecedeIgnoredFieldBinding(bool update, string field, bool anonymous)
    {
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, "\"" + field + "\":{},");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(MissingFields))]
    public async Task ParsedBodyField_DoesNotReplaceMissingRoute(string field)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, true, "\"" + field + "\":" + (field == "Id" ? "7007" : "\"2000-02-29\"") + ",", missing: true);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public void PublicTypedProjectionAndMvc_AgreeOnAcceptedAndRejectedPrimitiveShapes()
    {
        // A public 13.0.3 compatibility control. The effective historical deployed binary is unknown.
        var legacyOptions = new JsonSerializerSettings { NullValueHandling = NullValueHandling.Ignore, Culture = CultureInfo.InvariantCulture };
        foreach (var field in Fields)
        {
            foreach (var token in field == "Id" ? ValidIds : ValidDates)
            {
                var json = "{\"" + field + "\":" + token + "}";
                using var reader = new JsonTextReader(new StringReader(token)) { Culture = CultureInfo.InvariantCulture };
                object? typed = field == "Id" ? (object?)reader.ReadAsInt32() : reader.ReadAsDateTime();
                var projection = JsonConvert.DeserializeObject<PublicProjection>(json, legacyOptions)!;
                var actual = typeof(PublicProjection).GetProperty(field)!.GetValue(projection);
                Assert.Equal(typed ?? (field == "Id" ? (object)0 : null), actual);
                Assert.NotNull(JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>(json, Options));
            }
            foreach (var token in field == "Id" ? InvalidIds : InvalidDates)
            {
                var json = "{\"" + field + "\":" + token + "}";
                var originalError = Record.Exception(() => JsonConvert.DeserializeObject<PublicProjection>(json, legacyOptions));
                Assert.True(originalError is Newtonsoft.Json.JsonException or ArgumentOutOfRangeException);
                Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>(json, Options));
            }
        }
    }

    [Fact]
    public void IgnoredFields_AddNoClrRequestOrResponseWriteProperties()
    {
        var type = typeof(UpsertPurchaseOrderRequest);
        Assert.Equal(17, type.GetProperties().Length);
        foreach (var field in Fields) Assert.Null(type.GetProperty(field));
        var value = JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Id\":7007,\"CreatedDate\":\"2000-02-29\",\"ModifiedDate\":\"2000-02-29\",\"Notes\":true}", Options)!;
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(value, Options));
        Assert.Equal(new[] { "Notes" }, wire.RootElement.EnumerateObject().Select(property => property.Name).ToArray());
        Assert.Equal("true", wire.RootElement.GetProperty("Notes").GetString());
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"Notes\":true}"));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<PurchaseOrderResponse>("{\"CreatedDate\":true}", Options));
    }

    [Theory]
    [InlineData("en-US")]
    [InlineData("th-TH")]
    public void CurrentCulture_CannotChangePublicInvariantIgnoredDateParsing(string culture)
    {
        var previous = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(culture);
            using var slash = new JsonTextReader(new StringReader("\"02/03/2000\"")) { Culture = CultureInfo.InvariantCulture };
            Assert.Equal(new DateTime(2000, 2, 3), slash.ReadAsDateTime());
            using var midnight = new JsonTextReader(new StringReader("\"2000-02-29T24:00:00Z\"")) { Culture = CultureInfo.InvariantCulture };
            Assert.Equal(new DateTime(2000, 3, 1, 0, 0, 0, DateTimeKind.Utc), midnight.ReadAsDateTime());
            foreach (var field in Fields.Where(field => field != "Id"))
            {
                foreach (var token in ValidDates)
                    Assert.NotNull(JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"" + field + "\":" + token + "}", Options));
                foreach (var token in InvalidDates)
                    Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>("{\"" + field + "\":" + token + "}", Options));
            }
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Theory]
    [MemberData(nameof(MalformedFields))]
    public void MalformedIgnoredFields_PreserveExistingWholeHeaderSyntaxFailure(string field, bool unterminatedString)
    {
        var payload = "{\"" + field + "\":" + (unterminatedString ? "\"unterminated" : "");
        var expected = Assert.ThrowsAny<JsonException>(() => JsonDocument.Parse(payload));
        var actual = Assert.ThrowsAny<JsonException>(() => JsonSerializer.Deserialize<UpsertPurchaseOrderRequest>(payload, Options));
        Assert.Equal(expected.LineNumber, actual.LineNumber);
        Assert.Equal(expected.BytePositionInLine, actual.BytePositionInLine);
        Assert.Equal(expected.Path ?? "$", actual.Path);
    }

    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.PurchaseOrdersCreate, ProcurementPermissions.PurchaseOrdersUpdate, ProcurementPermissions.PurchaseOrdersRead);

    private Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, string members, bool missing = false)
    {
        var payload = "{" + members + "\"SupplierId\":7002,\"ShippingAddressId\":7003,\"BillingAddressId\":7003,\"EmployeeId\":123,"
            + "\"SupplierContactPerson\":\"supplier\",\"ShippingContactPerson\":\"shipping\",\"Notes\":true}";
        // Each HTTP body is disposed after its awaited send; callers dispose every response.
        return SendCoreAsync(client, update, missing, payload);
    }

    private static async Task<HttpResponseMessage> SendCoreAsync(HttpClient client, bool update, bool missing, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return update ? await client.PutAsync("/PurchaseOrders/" + (missing ? 999999 : 7004), content)
            : await client.PostAsync("/PurchaseOrders", content);
    }

    private async Task AssertAppliedAsync(bool update, string members)
    {
        using var client = Writer();
        var before = await SnapshotAsync(update ? 7004 : null);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, members);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = update ? 7004 : (await response.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!.Id;
        Assert.NotEqual(7007, id);
        if (!update)
        {
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!.Id);
        }
        using var read = await client.GetAsync("/PurchaseOrders/" + id);
        Assert.Equal(HttpStatusCode.OK, read.StatusCode);
        var current = (await read.Content.ReadFromJsonAsync<PurchaseOrderResponse>())!;
        Assert.Equal(id, current.Id);
        Assert.Equal("true", current.Notes);
        Assert.Equal(update ? "supplier" : "shipping", current.SupplierContactPerson);
        Assert.Equal("shipping", current.ShippingContactPerson);
        Assert.Equal(7002, current.SupplierId);
        Assert.Equal(7003, current.ShippingAddressId);
        Assert.Equal(7003, current.BillingAddressId);
        Assert.Equal(123, current.EmployeeId);
        Assert.Equal(update ? Now().AddSeconds(-1).AddDays(-2) : Now(), current.CreatedDate);
        Assert.Equal(Now(), current.ModifiedDate);
        await using var scope = app.Services.CreateAsyncScope();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        var row = await orders.PurchaseOrders.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(current.Notes, row.Notes);
        Assert.Equal(current.SupplierContactPerson, row.SupplierContactPerson);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    private async Task AssertRefusedAsync(bool update, string members, HttpStatusCode status)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, members);
        Assert.Equal(status, response.StatusCode);
        Assert.DoesNotContain("SYNTHETIC-PRIVATE-HEADER", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
    }

    private async Task<string> SnapshotAsync(int? excludedOrder = null)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Orders = await orders.PurchaseOrders.AsNoTracking().Where(value => excludedOrder == null || value.Id != excludedOrder).OrderBy(value => value.Id).ToArrayAsync(),
            Addresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Items = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }

    private sealed class PublicProjection
    {
        public int Id { get; set; }
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }
    }
}
