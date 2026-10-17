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

public sealed class ProcurementSupplierIgnoredAuditTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private static readonly string[] Fields = ["CreatedDate", "ModifiedDate"];
    private static readonly string[] ValidDates = ["null", "\"\"", "\"2000-02-29\"", "\"2000-02-29T12:34:56Z\"", "\"2000-02-29T12:34:56+07:00\"", "\"/Date(0)/\"", "\"2000-02-29T24:00:00Z\"", "\"02/03/2000\"", "\"2000-02-29T12:34:56.1234567Z\"", "\"/Date(0+0700)/\""];
    private static readonly string[] InvalidDates = ["0", "-1", "1.5", "true", "false", "[]", "{}", "\"SYNTHETIC-PRIVATE-SUPPLIER-AUDIT-DATE\"", "\"2000-02-30\"", "\"2000-13-01\"", "\"2000-02-29T24:00:01Z\"", "\"9999-12-31T24:00:00Z\""];
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
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "sentinel", AddressId = 7001, CreatedDate = Now().AddDays(-2), ModifiedDate = Now().AddDays(-1) });
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
                throw new AggregateException("Ignored supplier audit initialization and cleanup both failed.", initializationFailure, cleanupFailure);
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
        => Fields.SelectMany(field => (valid ? ValidDates : InvalidDates)
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
        var valid = "\"2000-02-29T12:34:56Z\"";
        var badScalar = "\"2000-02-30\"";
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
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.SuppliersRead);
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
        using var response = await SendAsync(client, true, "\"" + field + "\":" + "\"2000-02-29\"" + ",", missing: true);
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
            foreach (var token in ValidDates)
            {
                var json = "{\"" + field + "\":" + token + "}";
                using var reader = new JsonTextReader(new StringReader(token)) { Culture = CultureInfo.InvariantCulture };
                object? typed = reader.ReadAsDateTime();
                var projection = JsonConvert.DeserializeObject<PublicProjection>(json, legacyOptions)!;
                var actual = typeof(PublicProjection).GetProperty(field)!.GetValue(projection);
                Assert.Equal(typed, actual);
                Assert.NotNull(JsonSerializer.Deserialize<UpsertSupplierRequest>(json, Options));
            }
            foreach (var token in InvalidDates)
            {
                var json = "{\"" + field + "\":" + token + "}";
                var originalError = Record.Exception(() => JsonConvert.DeserializeObject<PublicProjection>(json, legacyOptions));
                Assert.True(originalError is Newtonsoft.Json.JsonException or ArgumentOutOfRangeException);
                Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertSupplierRequest>(json, Options));
            }
        }
    }

    [Fact]
    public void IgnoredFields_AddNoClrRequestOrResponseWriteProperties()
    {
        var type = typeof(UpsertSupplierRequest);
        Assert.Equal(8, type.GetProperties().Length);
        foreach (var field in Fields) Assert.Null(type.GetProperty(field));
        var value = JsonSerializer.Deserialize<UpsertSupplierRequest>("{\"Id\":7007,\"CreatedDate\":\"2000-02-29\",\"ModifiedDate\":\"2000-02-29\",\"Note\":true}", Options)!;
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(value, Options));
        Assert.Equal(new[] { "Note" }, wire.RootElement.EnumerateObject().Select(property => property.Name).ToArray());
        Assert.Equal("true", wire.RootElement.GetProperty("Note").GetString());
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertSupplierRequest>("{\"Note\":true}"));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SupplierResponse>("{\"CreatedDate\":true}", Options));
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
            foreach (var field in Fields)
            {
                foreach (var token in ValidDates)
                    Assert.NotNull(JsonSerializer.Deserialize<UpsertSupplierRequest>("{\"" + field + "\":" + token + "}", Options));
                foreach (var token in InvalidDates)
                    Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<UpsertSupplierRequest>("{\"" + field + "\":" + token + "}", Options));
            }
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Theory]
    [MemberData(nameof(MalformedFields))]
    public void MalformedIgnoredFields_PreserveExistingWholeSupplierSyntaxFailure(string field, bool unterminatedString)
    {
        var payload = "{\"" + field + "\":" + (unterminatedString ? "\"unterminated" : "");
        var expected = Assert.ThrowsAny<JsonException>(() => JsonDocument.Parse(payload));
        var actual = Assert.ThrowsAny<JsonException>(() => JsonSerializer.Deserialize<UpsertSupplierRequest>(payload, Options));
        Assert.Equal(expected.LineNumber, actual.LineNumber);
        Assert.Equal(expected.BytePositionInLine, actual.BytePositionInLine);
        Assert.Equal(expected.Path ?? "$", actual.Path);
    }

    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead);

    private Task<HttpResponseMessage> SendAsync(HttpClient client, bool update, string members, bool missing = false)
        => SendCoreAsync(client, update, missing, "{" + members
            + "\"Name\":\"ชื่อไทย\",\"Website\":12.3400E+03,\"TaxNumber\":123,\"Email\":\"synthetic@example.invalid\","
            + "\"Note\":true,\"Telephone\":false,\"Mobile\":\"mobile\",\"Fax\":\"fax\"}");

    private static async Task<HttpResponseMessage> SendCoreAsync(HttpClient client, bool update, bool missing, string payload)
    {
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return update ? await client.PutAsync("/Suppliers/" + (missing ? 999999 : 7002), content)
            : await client.PostAsync("/Suppliers", content);
    }

    private async Task AssertAppliedAsync(bool update, string members)
    {
        using var client = Writer();
        var before = await SnapshotAsync(update ? 7002 : null);
        SupplierResponse? previous = update ? await client.GetFromJsonAsync<SupplierResponse>("/Suppliers/7002") : null;
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, update, members);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        var id = update ? 7002 : (await response.Content.ReadFromJsonAsync<SupplierResponse>())!.Id;
        if (!update)
        {
            Assert.NotEqual(7002, id);
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
            Assert.Equal(id, (await location.Content.ReadFromJsonAsync<SupplierResponse>())!.Id);
        }
        using var read = await client.GetAsync("/Suppliers/" + id);
        Assert.Equal(HttpStatusCode.OK, read.StatusCode);
        var current = (await read.Content.ReadFromJsonAsync<SupplierResponse>())!;
        Assert.Equal(id, current.Id);
        Assert.Equal("ชื่อไทย", current.Name);
        Assert.Equal("12.3400E+03", current.Website);
        Assert.Equal("123", current.TaxNumber);
        Assert.Equal("synthetic@example.invalid", current.Email);
        Assert.Equal("true", current.Note);
        Assert.Equal("false", current.Telephone);
        Assert.Equal("mobile", current.Mobile);
        Assert.Equal("fax", current.Fax);
        Assert.Equal(update ? 7001 : (int?)null, current.AddressId);
        Assert.Equal(update ? previous!.CreatedDate : Now(), current.CreatedDate);
        Assert.Equal(Now(), current.ModifiedDate);
        if (update) Assert.True(current.ModifiedDate > previous!.ModifiedDate);
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var row = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.Equal(current.Id, row.Id);
        Assert.Equal(current.Name, row.Name);
        Assert.Equal(current.Website, row.Website);
        Assert.Equal(current.TaxNumber, row.TaxNumber);
        Assert.Equal(current.Email, row.Email);
        Assert.Equal(current.Note, row.Note);
        Assert.Equal(current.Telephone, row.Telephone);
        Assert.Equal(current.Mobile, row.Mobile);
        Assert.Equal(current.Fax, row.Fax);
        Assert.Equal(current.AddressId, row.AddressId);
        Assert.Equal(current.CreatedDate, row.CreatedDate);
        Assert.Equal(current.ModifiedDate, row.ModifiedDate);
        Assert.Equal(before, await SnapshotAsync(id));
    }

    private async Task AssertRefusedAsync(bool update, string members, HttpStatusCode status)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, update, members);
        Assert.Equal(status, response.StatusCode);
        Assert.DoesNotContain("SYNTHETIC-PRIVATE-SUPPLIER-AUDIT", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
    }

    private async Task<string> SnapshotAsync(int? excludedSupplier = null)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().Where(value => excludedSupplier == null || value.Id != excludedSupplier).OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Orders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Addresses = await orders.Addresses.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Items = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task CreateBranchesAndReplay_KeepEightFieldFingerprintAndServerDates(bool durable, bool withKey)
    {
        await using var branch = fixture.CreateFactory(true);
        branch.WorkloadSettings = new Dictionary<string, string?> { ["Procurement:DurableCreates:Enabled"] = durable.ToString() };
        using var client = fixture.ClientAs(branch, "service:procurement-parity",
            ProcurementPermissions.SuppliersCreate, ProcurementPermissions.SuppliersUpdate, ProcurementPermissions.SuppliersRead);
        var key = "supplier-audits-" + Guid.NewGuid().ToString("N");
        var digest = System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(key));
        if (withKey) client.DefaultRequestHeaders.Add("Idempotency-Key", key);
        var before = await SnapshotAsync();
        var payload = "{\"CreatedDate\":\"2000-02-29\",\"ModifiedDate\":\"2000-02-29\","
            + "\"Name\":\"branch\",\"Note\":true}";
        using var firstContent = new StringContent(payload, Encoding.UTF8, "application/json");
        using var first = await client.PostAsync("/Suppliers", firstContent);
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        var firstWire = await first.Content.ReadAsStringAsync();
        var created = JsonSerializer.Deserialize<SupplierResponse>(firstWire)!;
        Assert.Equal(Now(), created.CreatedDate);
        Assert.Equal(Now(), created.ModifiedDate);
        Assert.Null(created.AddressId);
        Assert.NotNull(first.Headers.Location);
        using var location = await client.GetAsync(first.Headers.Location);
        Assert.Equal(created, await location.Content.ReadFromJsonAsync<SupplierResponse>());
        var journal = await SupplierReceiptAsync(branch, digest);
        if (durable && withKey)
        {
            Assert.NotNull(journal);
            using var record = JsonDocument.Parse(journal);
            Assert.Equal(1, record.RootElement.GetProperty("CanonicalVersion").GetInt32());
            Assert.Equal(1, record.RootElement.GetProperty("ResponseVersion").GetInt32());
            Assert.Equal(created.Id, record.RootElement.GetProperty("EntityId").GetInt32());
            var canonical = JsonSerializer.SerializeToUtf8Bytes(
                new UpsertSupplierRequest("branch", null, null, null, "true", null, null, null),
                new JsonSerializerOptions { PropertyNamingPolicy = null });
            var tagged = new byte[canonical.Length + 2];
            tagged[0] = 1;
            tagged[1] = 1;
            canonical.CopyTo(tagged, 2);
            Assert.Equal("\\x" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(tagged)).ToLowerInvariant(),
                record.RootElement.GetProperty("PayloadDigest").GetString());
            Assert.Equal("\\x" + Convert.ToHexString(Encoding.UTF8.GetBytes(firstWire)).ToLowerInvariant(),
                record.RootElement.GetProperty("ResponseBody").GetString());
        }
        else Assert.Null(journal);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        if (withKey)
        {
            using var replayContent = new StringContent("{\"createddate\":null,\"modifieddate\":\"\","
                + "\"Name\":\"branch\",\"Note\":true}", Encoding.UTF8, "application/json");
            using var replay = await client.PostAsync("/Suppliers", replayContent);
            Assert.Equal(HttpStatusCode.Created, replay.StatusCode);
            Assert.Equal(firstWire, await replay.Content.ReadAsStringAsync());
            Assert.Equal(first.Headers.Location, replay.Headers.Location);
            Assert.Equal(journal, await SupplierReceiptAsync(branch, digest));
        }
        using var putContent = new StringContent("{\"CreatedDate\":\"1970-01-01\",\"ModifiedDate\":null,\"Name\":\"put\"}",
            Encoding.UTF8, "application/json");
        using var put = await client.PutAsync("/Suppliers/" + created.Id, putContent);
        Assert.Equal(HttpStatusCode.NoContent, put.StatusCode);
        using var read = await client.GetAsync("/Suppliers/" + created.Id);
        var updated = (await read.Content.ReadFromJsonAsync<SupplierResponse>())!;
        Assert.Equal("put", updated.Name);
        Assert.Equal(created.CreatedDate, updated.CreatedDate);
        Assert.Equal(Now(), updated.ModifiedDate);
        Assert.Equal(journal, await SupplierReceiptAsync(branch, digest));
        Assert.Equal(before, await SnapshotAsync(created.Id));
    }

    private static async Task<string?> SupplierReceiptAsync(ProcurementRuntimeFactory factory, byte[] keyDigest)
    {
        await using var scope = factory.Services.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        return await database.Database.SqlQueryRaw<string>(
            "SELECT row_to_json(receipt)::text AS \"Value\" FROM \"SupplierCreateReceipt\" AS receipt WHERE \"Operation\" = 1 AND \"KeyDigest\" = {0}",
            new object[] { keyDigest }).SingleOrDefaultAsync();
    }

    private sealed class PublicProjection
    {
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }
    }
}
