using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Legacy.Maliev.ProcurementService.Api.Authorization;
using Legacy.Maliev.ProcurementService.Application.Interfaces;
using Legacy.Maliev.ProcurementService.Application.Models;
using Legacy.Maliev.ProcurementService.Data;
using Legacy.Maliev.ProcurementService.Domain;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementAddressCountryIdBindingTests(ProcurementRuntimeFixture fixture)
    : IClassFixture<ProcurementRuntimeFixture>, IAsyncLifetime
{
    private ProcurementRuntimeFactory app = null!;
    private const string MarkerKey = "supplier:7002";
    private const string MarkerValue = "SYNTHETIC-COUNTRY-CACHE";
    private const string PrivateToken = "SYNTHETIC-PRIVATE-COUNTRY";
    private static readonly string[] Operations = ["supplier_post", "supplier_put", "address_post", "address_put"];
    private static readonly string[] Contracts = ["supplier", "address"];
    private JsonSerializerOptions Options => app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().Value.JsonSerializerOptions;
    private DateTime Now() => DateTime.SpecifyKind(fixture.Clock.GetUtcNow().UtcDateTime, DateTimeKind.Unspecified);

    private static readonly (string Kind, string Members, int Expected)[] ValidVectors =
    [
        ("number", "\"CountryId\":66,", 66),
        ("quoted", "\"CountryId\":\"66\",", 66),
        ("zero", "\"CountryId\":0,", 0),
        ("negative", "\"CountryId\":-66,", -66),
        ("minimum", "\"CountryId\":-2147483648,", int.MinValue),
        ("maximum", "\"CountryId\":2147483647,", int.MaxValue),
        ("omitted", "", 0),
        ("null_only", "\"CountryId\":null,", 0),
        ("null_after", "\"CountryId\":66,\"CountryId\":null,", 66),
        ("null_before", "\"CountryId\":null,\"CountryId\":66,", 66),
        ("null_between", "\"CountryId\":66,\"CountryId\":null,\"CountryId\":77,", 77),
        ("null_repeated", "\"CountryId\":null,\"CountryId\":null,", 0),
        ("case_mixed_null", "\"CountryId\":66,\"countryid\":null,", 66),
        ("last_value", "\"CountryId\":66,\"CountryId\":77,", 77),
        ("padded", "\"CountryId\":\" 66 \",", 66),
        ("padded_sign", "\"CountryId\":\" +0066 \",", 66),
        ("padded_negative", "\"CountryId\":\" -66 \",", -66),
        ("tab_line", "\"CountryId\":\"\\t66\\r\\n\",", 66),
        ("empty_only", "\"CountryId\":\"\",", 0),
        ("empty_after", "\"CountryId\":66,\"CountryId\":\"\",", 66),
        ("empty_before", "\"CountryId\":\"\",\"CountryId\":66,", 66),
        ("empty_between", "\"CountryId\":66,\"CountryId\":\"\",\"CountryId\":77,", 77),
        ("empty_and_null", "\"CountryId\":\"\",\"countryid\":null,", 0),
        ("padded_minimum", "\"CountryId\":\" -2147483648 \",", int.MinValue),
        ("padded_maximum", "\"CountryId\":\" +2147483647 \",", int.MaxValue),
    ];
    private static readonly string[] InvalidTokens =
    [
        "true", "false", "[]", "{}", "1.0", "1.5", "2147483648", "-2147483649",
        "\"2147483648\"", "\"1.0\"", "\" \"", "\"" + PrivateToken + "\"",
    ];
    private static readonly string[] NonNullTokens =
    [
        "66", "\"66\"", "\" 66 \"", "\"+66\"", "\"0066\"", "\"\"", "\" \"", "0", "-66",
        "2147483647", "-2147483648", "2147483648", "-2147483649", "1.0", "1.5",
        "true", "false", "[]", "{}", "\"" + PrivateToken + "\"",
    ];

    public static IEnumerable<object[]> ValidCountries => Operations.SelectMany(operation =>
        ValidVectors.Select(vector => new object[] { operation, vector.Kind, vector.Members, vector.Expected }));
    public static IEnumerable<object[]> InvalidCountries => Operations.SelectMany(operation =>
        InvalidTokens.Select(token => new object[] { operation, token }));
    public static IEnumerable<object[]> InvalidOccurrences => Operations.SelectMany(operation =>
        new[] { "{}", "2147483648", "\"" + PrivateToken + "\"" }.SelectMany(token =>
            new[] { new object[] { operation, token, false }, new object[] { operation, token, true } }));
    public static IEnumerable<object[]> DeniedCountries => Operations.SelectMany(operation =>
        new[] { new object[] { operation, false }, new object[] { operation, true } });
    public static IEnumerable<object[]> MissingCountries => Operations.Where(operation => operation != "address_post")
        .Select(operation => new object[] { operation });
    public static IEnumerable<object[]> ContractCases => Contracts.Select(contract => new object[] { contract });
    public static IEnumerable<object[]> MalformedCountries => Contracts.SelectMany(contract =>
        new[] { new object[] { contract, false }, new object[] { contract, true } });

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
                new SupplierAddress { Id = 7007, Address1 = "untouched", CountryId = 1 });
            suppliers.Suppliers.Add(new Supplier { Id = 7002, Name = "owner", AddressId = 7001, CreatedDate = Now(), ModifiedDate = Now() });
            await suppliers.SaveChangesAsync();
            var orders = scope.ServiceProvider.GetRequiredService<PurchaseOrderDbContext>();
            orders.Addresses.AddRange(
                new PurchaseOrderAddress { Id = 7003, AddressLine1 = "original", CountryId = 1, CreatedDate = Now(), ModifiedDate = Now() },
                new PurchaseOrderAddress { Id = 7007, AddressLine1 = "untouched", CountryId = 1 });
            orders.PurchaseOrders.Add(new PurchaseOrder { Id = 7004, SupplierId = 7002, ShippingAddressId = 7003, BillingAddressId = 7003 });
            orders.OrderItems.Add(new OrderItem { Id = 7005, PurchaseOrderId = 7004, PartNumber = "untouched" });
            orders.Files.Add(new PurchaseOrderFile { Id = 7006, PurchaseOrderId = 7004, Bucket = "untouched", ObjectName = "untouched" });
            await orders.SaveChangesAsync();
        }
        catch (Exception initializationFailure)
        {
            try { await DisposeAsync(); }
            catch (Exception cleanupFailure)
            {
                throw new AggregateException("Country input initialization and cleanup both failed.", initializationFailure, cleanupFailure);
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
    [MemberData(nameof(ValidCountries))]
    public async Task CountryScalarsAndIgnoredNulls_KeepPublicProjectionAndExistingWritePolicy(string operation, string caseId, string members, int expected)
    {
        Assert.NotEmpty(caseId);
        Assert.Equal(expected, PublicCountry(Payload(Contract(operation), members)));
        await AssertAppliedAsync(operation, members, expected);
    }

    [Theory]
    [MemberData(nameof(InvalidCountries))]
    public Task InvalidCountry_RefusesBeforeAnyStorageOrCacheMutation(string operation, string token)
        => AssertRefusedAsync(operation, "\"CountryId\":" + token + ",");

    [Theory]
    [MemberData(nameof(InvalidOccurrences))]
    public Task InvalidOccurrence_CannotBeHiddenByLaterValueOrNull(string operation, string token, bool last)
    {
        var members = last
            ? "\"CountryId\":66,\"CountryId\":" + token + ",\"CountryId\":null,"
            : "\"CountryId\":" + token + ",\"CountryId\":null,\"CountryId\":66,";
        return AssertRefusedAsync(operation, members);
    }

    [Theory]
    [MemberData(nameof(ContractCases))]
    public void IndependentNativeBefore_ExposesSourceCountryScalarAdmissionGaps(string contract)
    {
        var native = NativeMvcOptions();
        Assert.Equal(66, Country(JsonSerializer.Deserialize(Payload(contract, "\"CountryId\":66,"), RequestType(contract), native)!));
        foreach (var members in new[]
        {
            "\"CountryId\":66,\"CountryId\":null,",
            "\"CountryId\":\" +66 \",",
            "\"CountryId\":\"\",",
            "\"CountryId\":66,\"CountryId\":\"\",",
        })
        {
            var body = Payload(contract, members);
            var expected = PublicCountry(body);
            Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, RequestType(contract), native));
            Assert.Equal(expected, Country(JsonSerializer.Deserialize(body, RequestType(contract), Options)!));
        }
    }

    [Theory]
    [MemberData(nameof(ContractCases))]
    public void StandardScalarFamily_MatchesThePinnedPublicTypedReader(string contract)
    {
        foreach (var token in NonNullTokens)
        {
            var body = Payload(contract, "\"CountryId\":" + token + ",");
            var expected = 0;
            var failure = Record.Exception(() => { expected = PublicCountry(body); });
            if (failure is null)
            {
                Assert.Equal(expected, Country(JsonSerializer.Deserialize(body, RequestType(contract), Options)!));
            }
            else
            {
                Assert.IsAssignableFrom<Newtonsoft.Json.JsonException>(failure);
                var actual = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, RequestType(contract), Options));
                var native = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, RequestType(contract), NativeMvcOptions()));
                Assert.Equal(native.Path, actual.Path);
                Assert.Equal(native.LineNumber, actual.LineNumber);
                Assert.Equal(native.BytePositionInLine, actual.BytePositionInLine);
            }
        }
    }

    [Theory]
    [MemberData(nameof(DeniedCountries))]
    public async Task RealAuthenticationAndPermissionChecks_PrecedeCountryAdmission(string operation, bool anonymous)
    {
        using var client = anonymous ? app.CreateClient() : fixture.ClientAs(app, "service:procurement-parity", ProcurementPermissions.SuppliersRead);
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, Payload(Contract(operation), "\"CountryId\":null,\"CountryId\":{},"));
        Assert.Equal(anonymous ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
    }

    [Theory]
    [MemberData(nameof(MissingCountries))]
    public async Task ParsedCountry_DoesNotReplaceMissingRouteOrOwner(string operation)
    {
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, Payload(Contract(operation), "\"CountryId\":66,\"CountryId\":null,"), true);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
    }

    [Theory]
    [InlineData("supplier_post", "")]
    [InlineData("supplier_post", null)]
    [InlineData("address_post", null)]
    [InlineData("address_put", null)]
    public async Task ExistingRequiredLineGuards_RemainAuthoritative(string operation, string? line)
    {
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, Payload(Contract(operation), "\"CountryId\":66,\"CountryId\":null,", line));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
    }

    [Theory]
    [MemberData(nameof(MalformedCountries))]
    public void MalformedCountrySyntax_RetainsNativePathLineAndPosition(string contract, bool unterminated)
    {
        var body = Payload(contract, "")[..^1] + ",\"CountryId\":" + (unterminated ? "\"unterminated" : "");
        var expected = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, RequestType(contract), NativeMvcOptions()));
        var actual = Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, RequestType(contract), Options));
        Assert.Equal(expected.Path, actual.Path);
        Assert.Equal(expected.LineNumber, actual.LineNumber);
        Assert.Equal(expected.BytePositionInLine, actual.BytePositionInLine);
    }

    [Theory]
    [MemberData(nameof(ContractCases))]
    public void ClrIntAndDefaultWriter_KeepTheNativeContract(string contract)
    {
        var type = RequestType(contract);
        Assert.Equal(7, type.GetProperties().Length);
        Assert.Equal(typeof(int), type.GetProperty("CountryId")!.PropertyType);
        var native = NativeMvcOptions();
        foreach (var country in new[] { 0, 66, int.MinValue })
        {
            var value = JsonSerializer.Deserialize(Payload(contract, "\"CountryId\":" + country.ToString(CultureInfo.InvariantCulture) + ","), type, native)!;
            Assert.Equal(JsonSerializer.Serialize(value, type, native), JsonSerializer.Serialize(value, type, Options));
            using var wire = JsonDocument.Parse(JsonSerializer.Serialize(value, type, Options));
            Assert.Equal(JsonValueKind.Number, wire.RootElement.GetProperty("CountryId").ValueKind);
            Assert.Equal(country, wire.RootElement.GetProperty("CountryId").GetInt32());
            Assert.False(wire.RootElement.TryGetProperty("Id", out _));
            Assert.False(wire.RootElement.TryGetProperty("CreatedDate", out _));
            Assert.False(wire.RootElement.TryGetProperty("ModifiedDate", out _));
        }
    }

    [Theory]
    [InlineData("en-US")]
    [InlineData("th-TH")]
    public void PublicIntegerAdmission_DoesNotDependOnCurrentCulture(string culture)
    {
        var previous = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(culture);
            foreach (var contract in Contracts)
            {
                foreach (var members in new[] { "\"CountryId\":66,\"CountryId\":null,", "\"CountryId\":\" +66 \"," })
                {
                    var body = Payload(contract, members);
                    Assert.Equal(66, PublicCountry(body));
                    Assert.Equal(66, Country(JsonSerializer.Deserialize(body, RequestType(contract), Options)!));
                }
            }
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Fact]
    public async Task CountryAdmission_RemainsMvcRequestLocalAndOpenApiIntShapeIsUnchanged()
    {
        Assert.DoesNotContain(Options.Converters, converter => converter.GetType().Name == "AddressCountryIdJsonConverter");
        var minimal = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value.SerializerOptions;
        foreach (var contract in Contracts)
        {
            var type = RequestType(contract);
            var nativeProperty = Assert.Single(minimal.GetTypeInfo(type).Properties, property => property.Name == "CountryId");
            Assert.Equal(typeof(int), nativeProperty.PropertyType);
            Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(Payload(contract, "\"CountryId\":null,"), type, minimal));
        }
        foreach (var type in new[] { typeof(SupplierAddressResponse), typeof(PurchaseOrderAddressResponse) })
        {
            Assert.DoesNotContain(Options.GetTypeInfo(type).Properties, property => property.CustomConverter?.GetType().Name == "AddressCountryIdJsonConverter");
            Assert.Throws<JsonException>(() => JsonSerializer.Deserialize("{\"CountryId\":null}", type, Options));
        }
        await using var development = app.WithWebHostBuilder(builder => builder.UseEnvironment("Development"));
        using var client = development.CreateClient();
        using var response = await client.GetAsync("/procurement/openapi/v1.json");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var document = JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject();
        foreach (var (path, method) in new[]
        {
            ("/suppliers/{supplierId}/addresses", "post"), ("/suppliers/addresses/{addressId}", "put"),
            ("/purchaseorders/addresses", "post"), ("/purchaseorders/addresses/{addressId}", "put"),
        })
        {
            var item = Assert.Single(document["paths"]!.AsObject(), item => string.Equals(item.Key, path, StringComparison.OrdinalIgnoreCase)).Value!;
            var schema = Resolve(document, item[method]!["requestBody"]!["content"]!["application/json"]!["schema"]!.AsObject());
            Assert.Equal(7, schema["properties"]!.AsObject().Count);
            var country = Resolve(document, schema["properties"]!["CountryId"]!.AsObject());
            string[] types = country["type"] is JsonArray array ? array.Select(value => value!.GetValue<string>()).ToArray() : [country["type"]!.GetValue<string>()];
            Assert.Contains("integer", types);
            Assert.DoesNotContain("null", types);
            Assert.Equal("int32", country["format"]!.GetValue<string>());
        }
    }

    private static JsonObject Resolve(JsonObject document, JsonObject schema)
    {
        while (schema["$ref"] is JsonValue reference)
        {
            var path = reference.GetValue<string>();
            Assert.StartsWith("#/components/schemas/", path, StringComparison.Ordinal);
            schema = document["components"]!["schemas"]![path["#/components/schemas/".Length..]]!.AsObject();
        }
        return schema;
    }

    private static int PublicCountry(string body) => Newtonsoft.Json.JsonConvert.DeserializeObject<CountryProjection>(body,
        new Newtonsoft.Json.JsonSerializerSettings { Culture = CultureInfo.InvariantCulture, NullValueHandling = Newtonsoft.Json.NullValueHandling.Ignore })!.CountryId;

    private sealed class CountryProjection
    {
        public int CountryId { get; set; }
    }

    private static string Contract(string operation) => operation.StartsWith("supplier", StringComparison.Ordinal) ? "supplier" : "address";
    private static Type RequestType(string contract) => contract == "supplier" ? typeof(UpsertSupplierAddressRequest) : typeof(UpsertPurchaseOrderAddressRequest);
    private static int Country(object value) => value is UpsertSupplierAddressRequest supplier ? supplier.CountryId : ((UpsertPurchaseOrderAddressRequest)value).CountryId;

    private static string Payload(string contract, string members, string? line = "line1")
        => "{" + members + "\"Building\":\"building\",\"" + (contract == "supplier" ? "Address1" : "AddressLine1") + "\":" + JsonSerializer.Serialize(line)
            + ",\"" + (contract == "supplier" ? "Address2" : "AddressLine2") + "\":\"line2\",\"City\":\"city\",\"State\":\"state\",\"PostalCode\":\"code\"}";

    private HttpClient Writer() => fixture.ClientAs(app, "service:procurement-parity",
        ProcurementPermissions.SupplierAddressesWrite, ProcurementPermissions.SupplierAddressesRead,
        ProcurementPermissions.PurchaseOrderAddressesWrite, ProcurementPermissions.PurchaseOrderAddressesRead);

    private static async Task<HttpResponseMessage> SendAsync(HttpClient client, string operation, string body, bool missing = false)
    {
        var id = missing ? 999999 : operation == "supplier_put" ? 7001 : 7003;
        var owner = missing ? 999999 : 7002;
        using var request = new HttpRequestMessage(operation.EndsWith("put", StringComparison.Ordinal) ? HttpMethod.Put : HttpMethod.Post, operation switch
        {
            "supplier_post" => $"/suppliers/{owner}/addresses",
            "supplier_put" => $"/suppliers/addresses/{id}",
            "address_post" => "/purchaseorders/addresses",
            _ => $"/purchaseorders/addresses/{id}",
        });
        request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        return await client.SendAsync(request);
    }

    private async Task AssertRefusedAsync(string operation, string members)
    {
        var body = Payload(Contract(operation), members);
        Assert.ThrowsAny<Newtonsoft.Json.JsonException>(() => PublicCountry(body));
        using var client = Writer();
        await SetMarkerAsync();
        var before = await SnapshotAsync();
        using var response = await SendAsync(client, operation, body);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.DoesNotContain(PrivateToken, await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
        Assert.Equal(before, await SnapshotAsync());
        Assert.Equal(MarkerValue, await MarkerAsync());
    }

    private async Task AssertAppliedAsync(string operation, string members, int expected)
    {
        using var client = Writer();
        await SetMarkerAsync();
        var update = operation.EndsWith("put", StringComparison.Ordinal);
        var target = update ? operation == "supplier_put" ? 7001 : 7003 : 0;
        var before = await SnapshotAsync(operation, target);
        await using var initialScope = app.Services.CreateAsyncScope();
        var initialSuppliers = initialScope.ServiceProvider.GetRequiredService<SupplierDbContext>();
        var ownerBefore = await initialSuppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        using var response = await SendAsync(client, operation, Payload(Contract(operation), members));
        if (operation == "supplier_post" && expected == 0)
        {
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(before, await SnapshotAsync(operation, target));
            var owner = await initialSuppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
            Assert.Equal(JsonSerializer.Serialize(ownerBefore), JsonSerializer.Serialize(owner));
            Assert.Equal(MarkerValue, await MarkerAsync());
            return;
        }
        Assert.Equal(update ? HttpStatusCode.NoContent : HttpStatusCode.Created, response.StatusCode);
        if (!update)
        {
            using var created = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            target = created.RootElement.GetProperty("Id").GetInt32();
            Assert.True(target > 0);
            Assert.NotEqual(7007, target);
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
            Assert.Equal(expected, row.CountryId);
            Assert.Equal("building", row.Building);
            Assert.Equal("line1", row.Address1);
            Assert.Equal("line2", row.Address2);
            Assert.Equal("city", row.City);
            Assert.Equal("state", row.State);
            Assert.Equal("code", row.PostalCode);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
            var owner = await suppliers.Suppliers.AsNoTracking().SingleAsync(value => value.Id == 7002);
            if (!update)
            {
                Assert.Equal(target, owner.AddressId);
                Assert.Equal(Now(), owner.ModifiedDate);
                owner.AddressId = ownerBefore.AddressId;
                owner.ModifiedDate = ownerBefore.ModifiedDate;
            }
            Assert.Equal(JsonSerializer.Serialize(ownerBefore), JsonSerializer.Serialize(owner));
        }
        else
        {
            var row = await orders.Addresses.AsNoTracking().SingleAsync(value => value.Id == target);
            Assert.Equal(expected, row.CountryId);
            Assert.Equal("building", row.Building);
            Assert.Equal("line1", row.AddressLine1);
            Assert.Equal("line2", row.AddressLine2);
            Assert.Equal("city", row.City);
            Assert.Equal("state", row.State);
            Assert.Equal("code", row.PostalCode);
            Assert.Equal(update ? Now().AddSeconds(-1) : Now(), row.CreatedDate);
            Assert.Equal(Now(), row.ModifiedDate);
        }
        var uri = operation.StartsWith("supplier", StringComparison.Ordinal) ? "/suppliers/addresses/" : "/purchaseorders/addresses/";
        using var read = await client.GetAsync(uri + target.ToString(CultureInfo.InvariantCulture));
        Assert.Equal(HttpStatusCode.OK, read.StatusCode);
        using var wire = JsonDocument.Parse(await read.Content.ReadAsStringAsync());
        Assert.Equal(expected, wire.RootElement.GetProperty("CountryId").GetInt32());
        Assert.Equal(target, wire.RootElement.GetProperty("Id").GetInt32());
        Assert.Equal(before, await SnapshotAsync(operation, target));
        Assert.Equal(operation == "supplier_post" ? null : MarkerValue, await MarkerAsync());
    }

    private async Task SetMarkerAsync()
    {
        await using var scope = app.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<IProcurementCache>().SetAsync(MarkerKey, MarkerValue, TimeSpan.FromMinutes(1), CancellationToken.None);
    }

    private async Task<string?> MarkerAsync()
    {
        await using var scope = app.Services.CreateAsyncScope();
        return await scope.ServiceProvider.GetRequiredService<IProcurementCache>().GetAsync<string>(MarkerKey, CancellationToken.None);
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
            OrderAddresses = await orders.Addresses.AsNoTracking().Where(value => operation == null || operation.StartsWith("supplier") || value.Id != target).OrderBy(value => value.Id).ToArrayAsync(),
            Orders = await orders.PurchaseOrders.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Items = await orders.OrderItems.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
            Files = await orders.Files.AsNoTracking().OrderBy(value => value.Id).ToArrayAsync(),
        });
    }

    private JsonSerializerOptions NativeMvcOptions()
    {
        Assert.IsType<OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>(app.Services.GetRequiredService<IOptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>>());
        var setups = app.Services.GetServices<IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var posts = app.Services.GetServices<IPostConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var validations = app.Services.GetServices<IValidateOptions<Microsoft.AspNetCore.Mvc.JsonOptions>>().ToArray();
        var native = setups.Where(action => !IsOwnedConfigure(action)).ToArray();
        Assert.Single(setups, IsOwnedConfigure);
        var index = 0;
        foreach (var action in setups)
        {
            if (!IsOwnedConfigure(action)) Assert.Same(action, native[index++]);
        }
        Assert.Equal(native.Length, index);
        return new JsonSerializerOptions(new OptionsFactory<Microsoft.AspNetCore.Mvc.JsonOptions>(native, posts, validations)
            .Create(Microsoft.Extensions.Options.Options.DefaultName).JsonSerializerOptions);
    }

    private static bool IsOwnedConfigure(IConfigureOptions<Microsoft.AspNetCore.Mvc.JsonOptions> action)
        => action.GetType().FullName == "Legacy.Maliev.ProcurementService.Api.Serialization.ProcurementIgnoredBodyIdJsonOptions"
            && action.GetType().Assembly == typeof(ProcurementPermissions).Assembly;
}
