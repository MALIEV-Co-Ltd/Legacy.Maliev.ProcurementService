using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Api.Serialization;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementMetadataIgnoredAuditDateTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private ProcurementRuntimeFactory app = null!;
    private static readonly string[] Operations = ["supplier_post", "supplier_put", "address_post", "address_put", "file_put"];
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
            suppliers.Addresses.AddRange(
                new SupplierAddress { Id = 7001, Address1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new SupplierAddress { Id = 7007, Address1 = "untouched body identity", CountryId = 1 });
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "owner", AddressId = 7001, CreatedDate = Now(), ModifiedDate = Now() });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.AddRange(
                new PurchaseOrderAddress { Id = 7003, AddressLine1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderAddress { Id = 7007, AddressLine1 = "untouched body identity", CountryId = 1 });
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003 });
            orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "untouched" });
            orders.Files.AddRange(
                new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "original", ObjectName = "original", CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderFile { Id = 7007, PurchaseOrderId = 7004, Bucket = "untouched", ObjectName = "body identity" });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Ignored metadata audit initialization and cleanup both failed.", initializationFailure, cleanupFailure);
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

    private static readonly string[] Fields = ["CreatedDate", "ModifiedDate"];
    private static readonly string[] Contracts = ["supplier", "address", "file"];
    private static readonly string[] ValidDates = ["null", "\"\"", "\"2000-02-29\"", "\"2000-02-29T12:34:56Z\"", "\"2000-02-29T12:34:56+07:00\"", "\"/Date(0)/\"", "\"2000-02-29T24:00:00Z\"", "\"02/03/2000\"", "\"2000-02-29T12:34:56.1234567Z\"", "\"/Date(0+0700)/\""];
    private static readonly string[] InvalidDates = ["0", "-1", "1.5", "true", "false", "[]", "{}", "\"SYNTHETIC-PRIVATE-METADATA-AUDIT\"", "\"2000-02-30\"", "\"2000-13-01\"", "\"2000-02-29T24:00:01Z\"", "\"9999-12-31T24:00:00Z\""];
    private static IEnumerable<object[]> AuditCross(string[] tokens)
        => Operations.SelectMany(operation => Fields.SelectMany(propertyName => tokens.Select(token => new object[] { operation, propertyName, token })));
    public static IEnumerable<object[]> ValidAudits => AuditCross(ValidDates);
    public static IEnumerable<object[]> InvalidAudits => AuditCross(InvalidDates);
    public static IEnumerable<object[]> DuplicateAudits => Operations.SelectMany(operation => Fields.SelectMany(propertyName =>
        new[] { "bad_first", "bad_last", "bad_scalar_first", "bad_scalar_last", "null_first", "null_last" }
            .Select(mode => new object[] { operation, propertyName, mode })));
    public static IEnumerable<object[]> OmittedAudits => Operations.Select(operation => new object[] { operation });
    public static IEnumerable<object[]> DeniedAudits => Operations.SelectMany(operation => Fields.SelectMany(propertyName =>
        new[] { new object[] { operation, propertyName, false }, new object[] { operation, propertyName, true } }));
    public static IEnumerable<object[]> MissingAudits => Operations.Where(operation => operation != "address_post")
        .SelectMany(operation => Fields.Select(propertyName => new object[] { operation, propertyName }));
    public static IEnumerable<object[]> MalformedAudits => Contracts.SelectMany(contract => Fields.SelectMany(propertyName =>
        new[] { new object[] { contract, propertyName, false }, new object[] { contract, propertyName, true } }));
    public static IEnumerable<object[]> WriteContracts => Contracts.Select(contract => new object[] { contract });

    [Theory]
    [MemberData(nameof(ValidAudits))]
    public Task ParsedDates_AreDiscardedBeforeServerAuditAssignment(string operation, string field, string token)
        => AssertAppliedAsync(operation, "\"" + field.ToLowerInvariant() + "\":" + token + ",");

    [Theory]
    [MemberData(nameof(InvalidAudits))]
    public Task InvalidDate_RefusesBeforeStoredOrCachedStateCanChange(string operation, string field, string token)
        => AssertRefusedAsync(operation, "\"" + field + "\":" + token + ",");

    [Theory]
    [MemberData(nameof(DuplicateAudits))]
    public Task EveryDateOccurrence_IsValidatedBeforeDiscard(string operation, string field, string mode)
    {
        const string valid = "\"2000-02-29T12:34:56Z\"";
        var first = mode switch { "bad_first" => "{}", "bad_scalar_first" => "\"2000-02-30\"", "null_first" => "null", _ => valid };
        var last = mode switch { "bad_last" => "[]", "bad_scalar_last" => "\"2000-02-30\"", "null_last" => "null", _ => valid };
        var members = "\"" + field + "\":" + first + ",\"" + field.ToLowerInvariant() + "\":" + last + ",";
        return mode.StartsWith("bad", StringComparison.Ordinal) ? AssertRefusedAsync(operation, members) : AssertAppliedAsync(operation, members);
    }

    [Theory]
    [MemberData(nameof(OmittedAudits))]
    public Task OmittedDatesAndUnknownNestedGraphs_PreserveExistingWrites(string operation)
        => AssertAppliedAsync(operation, "\"Unknown\":{\"CreatedDate\":{},\"ModifiedDate\":[]},");

    [Theory]
    [MemberData(nameof(DeniedAudits))]
    public async Task AuthenticationAndAuthorization_PrecedeDateBinding(string operation, string field, bool anonymous)
    {
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.PurchaseOrdersRead);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, "\"" + field + "\":{},");
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Theory]
    [MemberData(nameof(MissingAudits))]
    public async Task ParsedDate_DoesNotReplaceMissingRouteOrParent(string operation, string field)
    {
        using var client = Writer();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, "\"" + field + "\":\"2000-02-29\",", missing: true);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
    }

    [Fact]
    public void PublicTypedProjectionAndIndependentNativeBefore_ExposeDiscardedDateValidationGap()
    {
        // Public pinned-reader compatibility only. The original deployed MVC binary is unknown.
        var legacy = new Newtonsoft.Json.JsonSerializerSettings { Culture = CultureInfo.InvariantCulture, NullValueHandling = Newtonsoft.Json.NullValueHandling.Ignore };
        var native = NativeMvcOptions();
        foreach (var contract in Contracts)
            foreach (var field in Fields)
            {
                var type = RequestType(contract);
                foreach (var token in ValidDates)
                {
                    using var reader = new Newtonsoft.Json.JsonTextReader(new StringReader(token)) { Culture = CultureInfo.InvariantCulture };
                    object? expected = reader.ReadAsDateTime();
                    var body = PlainPayload(contract, "\"" + field + "\":" + token + ",");
                    var projected = Newtonsoft.Json.JsonConvert.DeserializeObject<PublicAuditProjection>(body, legacy)!;
                    Assert.Equal(expected, typeof(PublicAuditProjection).GetProperty(field)!.GetValue(projected));
                    Assert.NotNull(JsonSerializer.Deserialize(body, type, native));
                    Assert.NotNull(JsonSerializer.Deserialize(body, type, Options));
                }
                foreach (var token in InvalidDates)
                {
                    var body = PlainPayload(contract, "\"" + field + "\":" + token + ",");
                    var sourceError = Record.Exception(() => Newtonsoft.Json.JsonConvert.DeserializeObject<PublicAuditProjection>(body, legacy));
                    Assert.True(sourceError is Newtonsoft.Json.JsonException or ArgumentOutOfRangeException);
                    Assert.NotNull(JsonSerializer.Deserialize(body, type, native));
                    Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, type, Options));
                }
            }
    }

    [Theory]
    [InlineData("en-US")]
    [InlineData("th-TH")]
    public void CurrentCulture_CannotChangeInvariantDateBinding(string culture)
    {
        var previous = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(culture);
            using var reader = new Newtonsoft.Json.JsonTextReader(new StringReader("\"02/03/2000\"")) { Culture = CultureInfo.InvariantCulture };
            Assert.Equal(new DateTime(2000, 2, 3), reader.ReadAsDateTime());
            foreach (var contract in Contracts)
                foreach (var field in Fields)
                {
                    foreach (var token in ValidDates)
                        Assert.NotNull(JsonSerializer.Deserialize(PlainPayload(contract, "\"" + field + "\":" + token + ","), RequestType(contract), Options));
                    foreach (var token in InvalidDates)
                        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(PlainPayload(contract, "\"" + field + "\":" + token + ","), RequestType(contract), Options));
                }
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Theory]
    [MemberData(nameof(MalformedAudits))]
    public void MalformedAuditSyntax_MatchesIndependentNativeDeclaredProperty(string contract, string field, bool unterminated)
    {
        var type = RequestType(contract);
        var native = new JsonSerializerOptions(NativeMvcOptions());
        native.TypeInfoResolver = native.TypeInfoResolver!.WithAddedModifier(metadata =>
        {
            if (metadata.Type != type) return;
            foreach (var propertyName in Fields)
            {
                var property = metadata.CreateJsonPropertyInfo(typeof(DateTime?), propertyName);
                property.Set = static (_, _) => { };
                property.Get = static _ => null;
                property.ShouldSerialize = static (_, _) => false;
                metadata.Properties.Add(property);
            }
        });
        Assert.All(native.GetTypeInfo(type).Properties.Where(property => Fields.Contains(property.Name)), property => Assert.Null(property.CustomConverter));
        var payload = "{\"" + field + "\":" + (unterminated ? "\"unterminated" : "");
        var expected = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(payload, type, native));
        var actual = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(payload, type, Options));
        Assert.Equal(expected.Path, actual.Path);
        Assert.Equal(expected.LineNumber, actual.LineNumber);
        Assert.Equal(expected.BytePositionInLine, actual.BytePositionInLine);
    }

    [Theory]
    [MemberData(nameof(WriteContracts))]
    public void ClrShapeAndNativeWriter_RemainUnchanged(string contract)
    {
        var type = RequestType(contract);
        Assert.Equal(contract == "file" ? 3 : 7, type.GetProperties().Length);
        foreach (var field in Fields) Assert.Null(type.GetProperty(field));
        var body = PlainPayload(contract, "\"Id\":7007,\"CreatedDate\":\"2000-02-29\",\"ModifiedDate\":\"2000-02-29\",");
        var native = NativeMvcOptions();
        var before = JsonSerializer.Deserialize(body, type, native)!;
        var current = JsonSerializer.Deserialize(body, type, Options)!;
        Assert.Equal(before, current);
        var expectedWire = JsonSerializer.Serialize(before, type, native);
        var actualWire = JsonSerializer.Serialize(current, type, Options);
        Assert.Equal(expectedWire, actualWire);
        using var document = JsonDocument.Parse(actualWire);
        foreach (var field in Fields) Assert.False(document.RootElement.TryGetProperty(field, out _));
        Assert.False(document.RootElement.TryGetProperty("Id", out _));
    }

    [Fact]
    public void AuditCompatibility_RemainsMvcRequestLocalAndResponsesKeepNativeDates()
    {
        Assert.Single(app.Services.GetServices<IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>(), IsOwnedConfigure);
        Assert.DoesNotContain(Options.Converters, converter => converter.GetType().Name == "IgnoredBodyNullableDateTimeJsonConverter");
        var minimal = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value.SerializerOptions;
        foreach (var contract in Contracts)
            Assert.NotNull(JsonSerializer.Deserialize(PlainPayload(contract, "\"CreatedDate\":true,\"ModifiedDate\":{},"), RequestType(contract), minimal));
        foreach (var type in new[] { typeof(SupplierAddressResponse), typeof(PurchaseOrderAddressResponse), typeof(PurchaseOrderFileResponse) })
        {
            Assert.DoesNotContain(Options.GetTypeInfo(type).Properties, property => property.CustomConverter?.GetType().Name == "IgnoredBodyNullableDateTimeJsonConverter");
            Assert.Throws<JsonException>(() => JsonSerializer.Deserialize("{\"CreatedDate\":true}", type, Options));
        }
    }

    private static Type RequestType(string contract) => contract switch
    {
        "supplier" => typeof(UpsertSupplierAddressRequest),
        "address" => typeof(UpsertPurchaseOrderAddressRequest),
        _ => typeof(UpsertPurchaseOrderFileRequest),
    };

    private static string PlainPayload(string contract, string members)
        => contract == "supplier" ? "{" + members + "\"Building\":\"building\",\"Address1\":\"line1\",\"Address2\":\"line2\",\"City\":\"city\",\"State\":\"state\",\"PostalCode\":\"code\",\"CountryId\":66}"
            : contract == "address" ? "{" + members + "\"Building\":\"building\",\"AddressLine1\":\"line1\",\"AddressLine2\":\"line2\",\"City\":\"city\",\"State\":\"state\",\"PostalCode\":\"code\",\"CountryId\":66}"
            : "{" + members + "\"PurchaseOrderId\":7004,\"Bucket\":\"bucket\",\"ObjectName\":\"object\"}";

    private async Task AssertRefusedAsync(string operation, string members)
    {
        using var client = Writer();
        var cachedBefore = await ReadExistingAsync(client, operation);
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, members);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.DoesNotContain("SYNTHETIC-PRIVATE-METADATA-AUDIT", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(cachedBefore, await ReadExistingAsync(client, operation));
    }

    private static async Task<string> ReadExistingAsync(HttpClient client, string operation)
    {
        var uri = operation.StartsWith("supplier", StringComparison.Ordinal) ? "/suppliers/addresses/7001"
            : operation == "file_put" ? "/purchaseorders/files/7006" : "/purchaseorders/addresses/7003";
        using var response = await client.GetAsync(uri);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return await response.Content.ReadAsStringAsync();
    }

    private sealed class PublicAuditProjection
    {
        public DateTime? CreatedDate { get; set; }
        public DateTime? ModifiedDate { get; set; }
    }

    private const string OwnedConfigure = "Legacy.Maliev.ProcurementService.Api.Serialization.ProcurementIgnoredBodyIdJsonOptions";

    private static bool IsOwnedConfigure(IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> action)
        => action.GetType().FullName == OwnedConfigure && action.GetType().Assembly == typeof(ProcurementPermissions).Assembly;

    private static Microsoft.AspNetCore.Mvc.JsonOptions ConstructNativeMvcOptions(
        IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] setups,
        IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] posts,
        IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>[] validations)
    {
        var nativeSetups = setups.Where(action => !IsOwnedConfigure(action)).ToArray();
        Assert.InRange(setups.Length - nativeSetups.Length, 0, 1);
        var index = 0;
        foreach (var action in setups)
        {
            if (IsOwnedConfigure(action)) continue;
            Assert.Same(action, nativeSetups[index++]);
        }
        Assert.Equal(nativeSetups.Length, index);
        // OptionsFactory preserves ordered named/default Configure actions, followed by
        // every PostConfigure and validator. No candidate resolver is inspected or unwrapped.
        return new OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>(nativeSetups, posts, validations)
            .Create(Microsoft.Extensions.Options.Options.DefaultName);
    }

    private JsonSerializerOptions NativeMvcOptions()
    {
        Assert.IsType<OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>(app.Services.GetRequiredService<IOptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>());
        var setups = app.Services.GetServices<IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var posts = app.Services.GetServices<IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var validations = app.Services.GetServices<IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var configured = ConstructNativeMvcOptions(setups, posts, validations);
        var native = new JsonSerializerOptions(configured.JsonSerializerOptions);
        // Historical0c/9005 controls already removed this exact pre-existing whole-DTO
        // converter. Keep that bounded native comparison policy on read-only baselines.
        for (var index = native.Converters.Count - 1; index >= 0; index--)
            if (native.Converters[index].GetType().FullName ==
                    "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter"
                && native.Converters[index].GetType().Assembly == typeof(ProcurementPermissions).Assembly)
                native.Converters.RemoveAt(index);
        foreach (var requestType in new[] { typeof(UpsertSupplierAddressRequest), typeof(UpsertPurchaseOrderAddressRequest), typeof(UpsertPurchaseOrderFileRequest) })
        {
            var metadata = native.GetTypeInfo(requestType);
            Assert.Equal(System.Text.Json.Serialization.Metadata.JsonTypeInfoKind.Object, metadata.Kind);
            Assert.DoesNotContain(metadata.Properties, property => property.Name is "Id" or "CreatedDate" or "ModifiedDate");
            Assert.DoesNotContain(metadata.Properties, property => property.CustomConverter?.GetType().FullName is
                "Legacy.Maliev.ProcurementService.Api.Serialization.IgnoredBodyInt32JsonConverter" or
                "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter");
        }
        return native;
    }

    private static bool IsOwnedPropertyReader(System.Text.Json.Serialization.JsonConverter? converter)
        => converter?.GetType().FullName is
            "Legacy.Maliev.ProcurementService.Api.Serialization.IgnoredBodyInt32JsonConverter" or
            "Legacy.Maliev.ProcurementService.Api.Serialization.PurchaseOrderFileMetadataRequestJsonConverter";

    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead,
        ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead,
        ProcurementPermissions.FilesWrite, ProcurementPermissions.FilesRead);

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string operation, string members, bool missing = false)
    {
        var target = missing ? 999999 : operation == "supplier_put" ? 7001 : operation == "address_put" ? 7003 : 7006;
        var owner = missing ? 999999 : 7002;
        var payload = operation.StartsWith("supplier", StringComparison.Ordinal)
            ? "{" + members + "\"Building\":true,\"Address1\":\"ชื่อไทย\",\"Address2\":1.2300E+03,\"CountryId\":66}"
            : operation == "file_put"
                ? "{" + members + "\"PurchaseOrderId\":7004,\"Bucket\":true,\"ObjectName\":1.2300E+03}"
                : "{" + members + "\"Building\":true,\"AddressLine1\":\"ชื่อไทย\",\"AddressLine2\":1.2300E+03,\"CountryId\":66}";
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        return operation switch
        {
            "supplier_post" => await client.PostAsync($"/suppliers/{owner}/addresses", content),
            "supplier_put" => await client.PutAsync($"/suppliers/addresses/{target}", content),
            "address_post" => await client.PostAsync("/purchaseorders/addresses", content),
            "address_put" => await client.PutAsync($"/purchaseorders/addresses/{target}", content),
            _ => await client.PutAsync($"/purchaseorders/files/{target}", content),
        };
    }

    private async Task AssertAppliedAsync(string operation, string members)
    {
        using var client = Writer();
        var update = operation.EndsWith("put", StringComparison.Ordinal);
        var target = operation == "supplier_put" ? 7001 : operation == "address_put" ? 7003 : operation == "file_put" ? 7006 : 0;
        var before = await SnapshotAsync(operation, target);
        await using var initialScope = app.Services.CreateAsyncScope();
        var initialSuppliers = initialScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var ownerBefore = await initialSuppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
        _ = await ReadExistingAsync(client, operation);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, operation, members);
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update)
        {
            using var created = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            target = created.RootElement.GetProperty("Id").GetInt32();
            Assert.InRange(target, 1, 100);
            Assert.NotNull(response.Headers.Location);
            using var location = await client.GetAsync(response.Headers.Location);
            Assert.Equal(HttpStatusCode.OK, location.StatusCode);
        }
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        if (operation.StartsWith("supplier", StringComparison.Ordinal))
        {
            var row = await suppliers.Addresses.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal("ชื่อไทย", row.Address1);
            Assert.Equal("true", row.Building);
            Assert.Equal("1.2300E+03", row.Address2);
            Assert.Equal(target, row.Id);
            Assert.Null(row.City);
            Assert.Null(row.State);
            Assert.Null(row.PostalCode);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(Now(), row.ModifiedDate);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            var ownerAfter = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
            Assert.Equal(ownerBefore.Name, ownerAfter.Name);
            Assert.Equal(ownerBefore.CreatedDate, ownerAfter.CreatedDate);
            Assert.Equal(ownerBefore.ModifiedDate, ownerAfter.ModifiedDate);
            Assert.Equal(update ? ownerBefore.AddressId : target, ownerAfter.AddressId);
            ownerAfter.AddressId = ownerBefore.AddressId;
            ownerAfter.ModifiedDate = ownerBefore.ModifiedDate;
            Assert.Equal(JsonSerializer.Serialize(ownerBefore), JsonSerializer.Serialize(ownerAfter));
        }
        else if (operation == "file_put")
        {
            var row = await orders.Files.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal(target, row.Id);
            Assert.Equal(7004, row.PurchaseOrderId);
            Assert.Equal("true", row.Bucket);
            Assert.Equal("1.2300E+03", row.ObjectName);
            Assert.Equal(Now().AddSeconds(-1), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
        }
        else
        {
            var row = await orders.Addresses.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal("ชื่อไทย", row.AddressLine1);
            Assert.Equal("true", row.Building);
            Assert.Equal("1.2300E+03", row.AddressLine2);
            Assert.Equal(66, row.CountryId);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
        }
        var readUri = operation.StartsWith("supplier", StringComparison.Ordinal) ? "/suppliers/addresses/" + target
            : operation == "file_put" ? "/purchaseorders/files/" + target : "/purchaseorders/addresses/" + target;
        using var fresh = await client.GetAsync(readUri);
        Assert.Equal(HttpStatusCode.OK, fresh.StatusCode);
        using var refreshed = JsonDocument.Parse(await fresh.Content.ReadAsStringAsync());
        Assert.Equal(target, refreshed.RootElement.GetProperty("Id").GetInt32());
        Assert.Equal(update ? Now().AddSeconds(-1) : Now(), refreshed.RootElement.GetProperty("CreatedDate").GetDateTime());
        Assert.Equal(Now(), refreshed.RootElement.GetProperty("ModifiedDate").GetDateTime());
        Assert.Equal(before, await SnapshotAsync(operation, target));
    }

    private async Task<string> SnapshotAsync(string? operation = null, int target = 0)
    {
        await using var scope = app.Services.CreateAsyncScope();
        var suppliers = scope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
        return JsonSerializer.Serialize(new
        {
            Suppliers = await suppliers.Suppliers.AsNoTracking().Where(value => operation != "supplier_post" || value.Id != 7002).OrderBy(value => value.Id).ToArrayAsync(),
            SupplierAddresses = await suppliers.Addresses.AsNoTracking().Where(value => operation == null || !operation.StartsWith("supplier") || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            PurchaseOrderAddresses = await orders.Addresses.AsNoTracking().Where(value => operation == null || !operation.StartsWith("address") || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
            OrderItems = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().Where(value => operation != "file_put" || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
        });
    }
}
